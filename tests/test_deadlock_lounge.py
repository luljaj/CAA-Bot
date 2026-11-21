import asyncio
import copy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import discord

os.environ.setdefault("GUILDID", "123")

from cogs import deadlock_lounge


class DeadlockLoungeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 0.0
        clock = patch.object(deadlock_lounge, "monotonic", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

        self.everyone = SimpleNamespace(id=1, name="@everyone")
        self.deadlock = SimpleNamespace(id=2, name="Deadlock")
        self.staff_role = SimpleNamespace(id=3, name="Staff Member")
        self.overwrites = {
            self.everyone.id: discord.PermissionOverwrite(view_channel=False, connect=False),
            self.deadlock.id: discord.PermissionOverwrite(view_channel=False, connect=True),
            self.staff_role.id: discord.PermissionOverwrite(view_channel=True, connect=True),
        }
        self.channel = SimpleNamespace(
            id=4,
            name="DL Lounge 2",
            members=[],
            voice_states={},
            overwrites_for=lambda role: copy.deepcopy(self.overwrites[role.id]),
            set_permissions=AsyncMock(side_effect=self.write_permissions),
        )
        roles = [self.everyone, self.deadlock, self.staff_role]
        self.guild = SimpleNamespace(
            id=deadlock_lounge.GUILD_ID,
            unavailable=False,
            voice_channels=[self.channel],
            roles=roles,
            get_channel=lambda channel_id: self.channel if channel_id == self.channel.id else None,
            get_role=lambda role_id: next((role for role in roles if role.id == role_id), None),
        )
        bot = SimpleNamespace(is_ready=lambda: True, get_guild=lambda guild_id: self.guild)
        self.cog = deadlock_lounge.DeadlockLounge(bot)
        self.staff = SimpleNamespace(id=5, guild=self.guild, roles=[self.staff_role])
        self.player = SimpleNamespace(id=6, guild=self.guild, roles=[self.deadlock])
        members = {self.staff.id: self.staff, self.player.id: self.player}
        self.guild.get_member = members.get

    async def write_permissions(self, role, *, overwrite, reason):
        self.overwrites[role.id] = overwrite

    async def move(self, member, before, after):
        if after is self.channel:
            self.channel.voice_states[member.id] = SimpleNamespace(channel=after)
        else:
            self.channel.voice_states.pop(member.id, None)
        await self.cog.on_voice_state_update(
            member, SimpleNamespace(channel=before), SimpleNamespace(channel=after)
        )

    def assert_visible(self, visible):
        self.assertIs(self.overwrites[self.deadlock.id].view_channel, visible)

    async def test_staff_opens_and_only_deadlock_view_channel_changes(self):
        await self.move(self.player, None, self.channel)
        await self.cog.sync_visibility()
        self.assert_visible(False)

        await self.move(self.staff, None, self.channel)
        await self.cog.sync_visibility()
        self.assert_visible(True)
        self.assertIs(self.channel.set_permissions.await_args.args[0], self.deadlock)
        self.assertTrue(self.overwrites[self.deadlock.id].connect)
        self.assertEqual(
            self.overwrites[self.everyone.id],
            discord.PermissionOverwrite(view_channel=False, connect=False),
        )
        self.assertEqual(
            self.overwrites[self.staff_role.id],
            discord.PermissionOverwrite(view_channel=True, connect=True),
        )

    async def test_last_departure_and_short_rejoin_restart_the_full_timer(self):
        await self.move(self.staff, None, self.channel)
        await self.cog.sync_visibility()
        await self.move(self.player, None, self.channel)
        await self.move(self.staff, self.channel, None)
        self.now = 900
        await self.cog.sync_visibility()
        self.assert_visible(True)

        await self.move(self.player, self.channel, None)
        self.now = 1499
        await self.move(self.player, None, self.channel)
        await self.move(self.player, self.channel, None)
        self.now = 2098
        await self.cog.sync_visibility()
        self.assert_visible(True)
        self.now = 2099
        await self.cog.sync_visibility()
        self.assert_visible(False)

    async def test_restart_gives_an_open_empty_channel_a_new_timer(self):
        self.overwrites[self.deadlock.id].view_channel = True
        self.now = 4000
        await self.cog.on_ready()
        await self.cog.sync_visibility()
        self.now = 4599
        await self.cog.sync_visibility()
        self.assert_visible(True)
        self.now = 4600
        await self.cog.sync_visibility()
        self.assert_visible(False)

    async def test_reconnect_restarts_the_idle_timer(self):
        self.overwrites[self.deadlock.id].view_channel = True
        await self.cog.sync_visibility()
        self.now = 599
        await self.cog.on_disconnect()
        self.now = 900
        await self.cog.sync_visibility()
        self.assert_visible(True)

        await self.cog.on_resumed()
        await self.cog.sync_visibility()
        self.now = 1500
        await self.cog.sync_visibility()
        self.assert_visible(False)

    async def test_join_during_close_restores_access(self):
        self.overwrites[self.deadlock.id].view_channel = True
        await self.cog.sync_visibility()
        request_started = asyncio.Event()
        allow_request = asyncio.Event()

        async def slow_write(role, *, overwrite, reason):
            request_started.set()
            await allow_request.wait()
            await self.write_permissions(role, overwrite=overwrite, reason=reason)

        self.channel.set_permissions.side_effect = slow_write
        self.now = 600
        close = asyncio.create_task(self.cog.sync_visibility())
        await asyncio.wait_for(request_started.wait(), timeout=1)
        await self.move(self.player, None, self.channel)
        allow_request.set()
        await close
        await self.cog.sync_visibility()
        self.assert_visible(True)

    async def test_failed_permission_update_is_retried(self):
        failure = discord.HTTPException(SimpleNamespace(status=500, reason="Error"), "Test failure")
        self.channel.set_permissions.side_effect = failure
        await self.move(self.staff, None, self.channel)
        with self.assertLogs(deadlock_lounge.logger, level="ERROR"):
            await self.cog.sync_visibility()
        self.assert_visible(False)

        self.channel.set_permissions.side_effect = self.write_permissions
        self.now = deadlock_lounge.RETRY_SECONDS
        await self.cog.sync_visibility()
        self.assert_visible(True)

    async def test_event_driven_worker_wakes_immediately_and_sleeps_when_idle(self):
        self.assertIsNone(await self.cog.sync_visibility())
        await self.cog.cog_load()
        try:
            await self.move(self.staff, None, self.channel)
            await asyncio.sleep(0)
            self.assert_visible(True)

            await self.move(self.staff, self.channel, None)
            delay = await self.cog.sync_visibility()
            self.assertEqual(delay, deadlock_lounge.IDLE_SECONDS)
        finally:
            await self.cog.cog_unload()
