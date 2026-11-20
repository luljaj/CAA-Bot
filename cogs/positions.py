"""Keep registered stats positions aligned with the configured Discord guild."""
import asyncio
from dataclasses import dataclass
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from position_utils import position_role

GUILD_ID = int(os.getenv("GUILDID"))
logger = logging.getLogger(__name__)
PAGE_SIZE = 500
WRITE_BATCH_SIZE = 50


@dataclass
class SyncResult:
    examined: int = 0
    changed: int = 0
    cleared: int = 0
    unchanged: int = 0
    failed: int = 0

    def summary(self):
        return ", ".join(f"{name}: {getattr(self, name)}" for name in self.__dataclass_fields__)


class Positions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase
        self._write_lock = asyncio.Lock()
        self._pending_ids = set()
        self._full_pending = False
        self._worker = None

    async def _execute(self, query):
        # Keep synchronous Supabase IO off the gateway loop. On cancellation, wait
        # for in-flight IO before releasing the write lock to another reconciler.
        task = asyncio.create_task(asyncio.to_thread(query.execute))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    def _start_worker(self):
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run_pending())

    def queue_member(self, user_id):
        self._pending_ids.add(int(user_id))
        self._start_worker()

    def queue_full(self):
        self._full_pending = True
        self._start_worker()

    async def _run_pending(self):
        while self._full_pending or self._pending_ids:
            try:
                if self._full_pending:
                    # Coalesce bursts of role edits and reconnect notifications.
                    await asyncio.sleep(1)
                    self._full_pending = False
                    await self.reconcile_all()
                else:
                    async with self._write_lock:
                        await self._replay_pending()
            except Exception:
                logger.exception("Background position reconciliation failed")

    async def cog_unload(self):
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    async def _registered_rows(self):
        rows = []
        offset = 0
        while True:
            response = await self._execute(
                self.supabase.table("stats").select("discordid,position")
                .order("discordid").range(offset, offset + PAGE_SIZE - 1)
            )
            page = response.data or []
            rows.extend(page)
            if not page:
                return rows
            # Advance by the returned size to also handle server-side row caps.
            offset += len(page)

    async def _write_position(self, row, desired, result):
        result.examined += 1
        if row.get("position") == desired:
            result.unchanged += 1
            return
        try:
            await self._execute(
                self.supabase.table("stats").update({"position": desired})
                .eq("discordid", row["discordid"])
            )
        except Exception:
            result.failed += 1
            logger.exception("Could not update position for %s", row["discordid"])
        else:
            result.changed += 1
            if desired is None:
                result.cleared += 1

    async def _reconcile_member(self, user_id):
        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            raise RuntimeError("Configured guild is unavailable")
        # Fetch at execution time instead of trusting an older gateway event.
        try:
            member = await guild.fetch_member(user_id)
        except discord.NotFound:
            member = None
        response = await self._execute(
            self.supabase.table("stats").select("discordid,position")
            .eq("discordid", user_id)
        )
        result = SyncResult()
        for row in response.data or []:
            await self._write_position(row, position_role(member).name if member else None, result)
        return result

    async def _replay_pending(self):
        while self._pending_ids:
            user_id = self._pending_ids.pop()
            try:
                await self._reconcile_member(user_id)
            except Exception:
                logger.exception("Could not reconcile member %s", user_id)

    async def reconcile_all(self):
        async with self._write_lock:
            guild = self.bot.get_guild(GUILD_ID)
            if guild is None:
                raise RuntimeError("Configured guild is unavailable")
            rows = await self._registered_rows()
            # No writes (especially clears) until the entire enumeration succeeds.
            members = {member.id: member async for member in guild.fetch_members(limit=None)}
            result = SyncResult()
            try:
                for start in range(0, len(rows), WRITE_BATCH_SIZE):
                    for row in rows[start:start + WRITE_BATCH_SIZE]:
                        member = members.get(int(row["discordid"]))
                        desired = position_role(member).name if member else None
                        await self._write_position(row, desired, result)
                    await asyncio.sleep(0)
            finally:
                # Events received during enumeration or writes override scan snapshots.
                await self._replay_pending()
            return result

    @app_commands.command(name="syncpositions", description="Synchronize registered positions from Discord roles.")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def syncpositions(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID or not interaction.permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission is required in the configured server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self.reconcile_all()
        except Exception:
            logger.exception("Manual position reconciliation failed")
            await interaction.followup.send("Position sync failed; see bot logs. No incomplete member scan is used to clear records.", ephemeral=True)
        else:
            await interaction.followup.send(result.summary(), ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        self.queue_full()

    @commands.Cog.listener()
    async def on_resumed(self):
        self.queue_full()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.guild.id == GUILD_ID:
            self.queue_member(member.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.guild.id == GUILD_ID:
            self.queue_member(member.id)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if after.guild.id == GUILD_ID and before.roles != after.roles:
            self.queue_member(after.id)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if after.guild.id == GUILD_ID and (before.name != after.name or before.position != after.position):
            self.queue_full()

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        if role.guild.id == GUILD_ID:
            self.queue_full()


async def setup(bot):
    await bot.add_cog(Positions(bot))
