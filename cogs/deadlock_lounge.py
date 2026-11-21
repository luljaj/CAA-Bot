import asyncio
from contextlib import suppress
import logging
import os
from time import monotonic

import discord
from discord.ext import commands

from config import DEADLOCK_ROLE_NAME, DL_LOUNGE_CHANNEL_NAME, STAFF_ROLE_NAMES

logger = logging.getLogger(__name__)
GUILD_ID = int(os.environ["GUILDID"])
IDLE_SECONDS = 10 * 60
RETRY_SECONDS = 30


def is_staff(member: discord.Member) -> bool:
    return any(role.name in STAFF_ROLE_NAMES for role in member.roles)


class DeadlockLounge(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._connected = bot.is_ready()
        self._visible: bool | None = None
        self._open_requested = False
        self._empty_since: float | None = None
        self._join_count = 0
        self._retry_at = 0.0
        self._generation = 0
        self._wake = asyncio.Event()
        self._worker: asyncio.Task | None = None

    async def cog_load(self):
        self._worker = asyncio.create_task(self._run_loop())

    async def cog_unload(self):
        if self._worker is not None:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    def _find_target(self) -> tuple[discord.VoiceChannel, discord.Role] | None:
        guild = self.bot.get_guild(GUILD_ID)
        if guild is None or guild.unavailable:
            return None

        channels = [channel for channel in guild.voice_channels if channel.name == DL_LOUNGE_CHANNEL_NAME]
        roles = [role for role in guild.roles if role.name == DEADLOCK_ROLE_NAME]
        if len(channels) != 1 or len(roles) != 1:
            return None
        return channels[0], roles[0]

    def _has_staff_connected(self, channel: discord.VoiceChannel) -> bool:
        guild = self.bot.get_guild(GUILD_ID)
        get_member = getattr(guild, "get_member", None)
        if callable(get_member):
            members = (get_member(user_id) for user_id in channel.voice_states)
            return any(member is not None and is_staff(member) for member in members)
        return any(is_staff(member) for member in channel.members)

    async def _run_loop(self):
        while True:
            self._wake.clear()
            try:
                delay = await self.sync_visibility()
            except Exception:
                logger.exception("Unexpected error syncing %s visibility", DL_LOUNGE_CHANNEL_NAME)
                delay = RETRY_SECONDS
            if self._wake.is_set():
                continue
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    @commands.Cog.listener()
    async def on_ready(self):
        self._generation += 1
        self._visible = None
        self._empty_since = None
        self._retry_at = 0.0
        self._connected = True
        if self._find_target() is None:
            logger.warning(
                "%s needs a unique voice channel and %s role in guild %s",
                DL_LOUNGE_CHANNEL_NAME,
                DEADLOCK_ROLE_NAME,
                GUILD_ID,
            )
        self._wake.set()

    @commands.Cog.listener()
    async def on_disconnect(self):
        self._connected = False
        self._empty_since = None
        self._wake.set()

    @commands.Cog.listener()
    async def on_resumed(self):
        self._connected = True
        self._wake.set()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.guild.id != GUILD_ID or before.channel == after.channel:
            return

        target = self._find_target()
        if target is None:
            return

        channel, _ = target
        if after.channel == channel:
            self._join_count += 1
            self._empty_since = None
            if is_staff(member):
                self._open_requested = True
            self._wake.set()
        elif before.channel == channel and not channel.voice_states:
            self._empty_since = monotonic()
            self._wake.set()

    async def sync_visibility(self) -> float | None:
        if not self._connected:
            return None

        target = self._find_target()
        if target is None:
            self._visible = None
            return None

        channel, role = target
        now = monotonic()
        if self._visible is None:
            self._visible = channel.overwrites_for(role).view_channel is True
            self._open_requested = self._open_requested or self._has_staff_connected(channel)
            self._retry_at = 0.0

        if channel.voice_states:
            self._empty_since = None
        elif self._empty_since is None:
            self._empty_since = now

        empty_since = self._empty_since
        expired = empty_since is not None and now - empty_since >= IDLE_SECONDS
        if expired:
            self._open_requested = False

        desired = (self._visible or self._open_requested) and not expired
        if desired == self._visible:
            if self._visible and empty_since is not None:
                return max(0.0, IDLE_SECONDS - (now - empty_since))
            return None
        if now < self._retry_at:
            return self._retry_at - now

        overwrite = channel.overwrites_for(role)
        overwrite.view_channel = desired
        generation = self._generation
        join_count = self._join_count
        reason = (
            f"Staff opened {DL_LOUNGE_CHANNEL_NAME}"
            if desired
            else f"{DL_LOUNGE_CHANNEL_NAME} was empty for ten minutes"
        )
        try:
            await channel.set_permissions(role, overwrite=overwrite, reason=reason)
        except discord.HTTPException:
            logger.exception("Could not update %s access to %s", DEADLOCK_ROLE_NAME, DL_LOUNGE_CHANNEL_NAME)
            if self._generation == generation:
                self._retry_at = monotonic() + RETRY_SECONDS
                return RETRY_SECONDS
            return 0.0

        if self._generation != generation:
            return 0.0

        # Discord updates the cached overwrite in a separate gateway event.
        self._visible = desired
        self._retry_at = 0.0
        if desired:
            self._open_requested = False
            if not channel.voice_states:
                self._empty_since = self._empty_since or monotonic()
                return max(0.0, IDLE_SECONDS - (monotonic() - self._empty_since))
            return None

        if self._join_count != join_count or channel.voice_states:
            # Restore access if a voice connection arrived during the permission request.
            self._open_requested = True
            return 0.0
        return None


async def setup(bot: commands.Bot):
    await bot.add_cog(DeadlockLounge(bot))
