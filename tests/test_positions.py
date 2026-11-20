"""Position sync tests use only in-memory Discord and Supabase fakes."""
import asyncio
import os
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GUILDID", "123")

import discord
from cogs import positions
from cogs.positions import Positions
from position_utils import position_role, schedule_position_sync


def member(uid, *names):
    roles = [NS(name="@everyone", color=0)] + [NS(name=name, color=i + 1) for i, name in enumerate(names)]
    return NS(id=uid, roles=roles, guild=NS(id=positions.GUILD_ID, default_role=roles[0]))


class Query:
    def __init__(self, db):
        self.db = db
        self.payload = None
        self.uid = None
        self.bounds = None

    def select(self, columns):
        assert columns == "discordid,position"
        return self

    def order(self, key):
        assert key == "discordid"
        return self

    def range(self, start, end):
        self.bounds = (start, end)
        return self

    def eq(self, key, value):
        assert key == "discordid"
        self.uid = int(value)
        return self

    def update(self, payload):
        assert set(payload) == {"position"}
        self.payload = payload
        return self

    def execute(self):
        if self.payload is not None:
            if self.uid in self.db.fail_ids:
                raise RuntimeError("write failed")
            self.db.writes.append((self.uid, self.payload.copy()))
            if self.uid in self.db.rows:
                self.db.rows[self.uid].update(self.payload)
            return NS(data=[])
        rows = [row.copy() for uid, row in sorted(self.db.rows.items()) if self.uid is None or uid == self.uid]
        if self.bounds:
            start, end = self.bounds
            self.db.pages.append(self.bounds)
            rows = rows[start:min(end + 1, start + self.db.cap)]
        return NS(data=rows)


class DB:
    def __init__(self, rows):
        self.rows = {uid: {"discordid": uid, "position": value} for uid, value in rows.items()}
        self.writes = []
        self.pages = []
        self.cap = 500
        self.fail_ids = set()

    def table(self, name):
        assert name == "stats"
        return Query(self)


class Guild:
    def __init__(self, members):
        self.members = {m.id: m for m in members}
        self.scan_hook = None
        self.partial_fail = False
        self.scans = 0

    async def fetch_members(self, limit):
        assert limit is None
        self.scans += 1
        for m in list(self.members.values()):
            yield m
            if self.scan_hook:
                hook, self.scan_hook = self.scan_hook, None
                await hook()
            if self.partial_fail:
                raise RuntimeError("interrupted enumeration")

    async def fetch_member(self, uid):
        if uid not in self.members:
            raise discord.NotFound(NS(status=404, reason="Not Found"), "departed")
        return self.members[uid]


class PositionTests(unittest.IsolatedAsyncioTestCase):
    def make_cog(self, rows, members):
        self.db = DB(rows)
        self.guild = Guild(members)
        self.bot = NS(supabase=self.db, get_guild=lambda uid: self.guild)
        return Positions(self.bot)

    def test_highest_eligible_and_fallback(self):
        m = member(1, "Intern", "Content Creator", "Event Winner", "Server Booster")
        original = list(m.roles)
        self.assertEqual(position_role(m).name, "Intern")
        self.assertEqual(m.roles, original)
        self.assertEqual(position_role(member(2, "Content Creator", "Event Winner", "Server Booster")).name, "@everyone")
        self.assertEqual(position_role(member(3, "content creator")).name, "content creator")
        self.assertEqual(position_role(member(4, "Intern", "Director")).name, "Director")

    async def test_full_sync_changes_only_registered_and_idempotence(self):
        cog = self.make_cog({1: "Intern", 2: "Director", 3: "Director", 4: None},
                            [member(1, "Director"), member(2, "Intern"), member(4, "Content Creator"), member(99, "Director")])
        result = await cog.reconcile_all()
        self.assertEqual((result.examined, result.changed, result.cleared, result.unchanged, result.failed), (4, 4, 1, 0, 0))
        self.assertEqual([self.db.rows[i]["position"] for i in range(1, 5)], ["Director", "Intern", None, "@everyone"])
        self.assertNotIn(99, self.db.rows)
        self.db.writes.clear()
        result = await cog.reconcile_all()
        self.assertEqual((result.changed, result.unchanged), (0, 4))
        self.assertEqual(self.db.writes, [])

    async def test_partial_enumeration_never_clears_or_writes(self):
        cog = self.make_cog({1: "old", 2: "keep"}, [member(1, "Director")])
        self.guild.partial_fail = True
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            await cog.reconcile_all()
        self.assertEqual(self.db.writes, [])
        self.assertEqual(self.db.rows[2]["position"], "keep")

    async def test_missing_discord_id_skipped_while_other_rows_sync(self):
        cog = self.make_cog({2: None}, [member(2, "Director")])
        rows = [{"discordid": None, "position": "keep"}, self.db.rows[2].copy()]
        with patch.object(cog, "_registered_rows", AsyncMock(return_value=rows)):
            result = await cog.reconcile_all()
        self.assertEqual(self.db.writes, [(2, {"position": "Director"})])
        self.assertEqual((result.examined, result.skipped, result.changed, result.failed), (2, 1, 1, 0))

    async def test_event_during_scan_replays_fresh_state(self):
        cog = self.make_cog({1: "old"}, [member(1, "Intern")])
        async def change():
            self.guild.members[1] = member(1, "Director")
            # Preserve event queuing while leaving replay to the scan's lock owner.
            with patch.object(cog, "_start_worker"):
                cog.queue_member(1)
        self.guild.scan_hook = change
        await cog.reconcile_all()
        self.assertEqual(self.db.rows[1]["position"], "Director")
        self.assertEqual(self.db.writes[-1], (1, {"position": "Director"}))
        self.assertEqual(cog._pending_ids, set())

    async def test_queued_event_worker_waits_for_scan_and_latest_state_wins(self):
        cog = self.make_cog({1: "old"}, [member(1, "Director")])
        entered = asyncio.Event()
        release = asyncio.Event()

        async def pause_scan():
            entered.set()
            await release.wait()

        self.guild.scan_hook = pause_scan
        scan = asyncio.create_task(cog.reconcile_all())
        await entered.wait()
        before = self.guild.members[1]
        after = member(1, "Intern")
        self.guild.members[1] = after
        await cog.on_member_update(before, after)
        await asyncio.sleep(0)
        self.assertEqual(self.db.writes, [])
        release.set()
        await scan
        await cog._worker
        self.assertEqual(self.db.rows[1]["position"], "Intern")
        self.assertEqual(cog._pending_ids, set())

    async def test_gateway_event_filters_and_role_reconciliation(self):
        cog = self.make_cog({}, [])
        with patch.object(cog, "_start_worker"):
            await cog.on_member_join(member(1))
            await cog.on_member_remove(member(2))
            await cog.on_member_update(member(3, "Director"), member(3, "Intern"))
            await cog.on_member_update(member(4, "Intern"), member(4, "Intern"))
            outsider = member(5)
            outsider.guild.id = positions.GUILD_ID + 1
            await cog.on_member_join(outsider)
            self.assertEqual(cog._pending_ids, {1, 2, 3})
            guild = NS(id=positions.GUILD_ID)
            await cog.on_guild_role_update(NS(name="Old", position=1), NS(name="New", position=1, guild=guild))
            self.assertTrue(cog._full_pending)
            cog._full_pending = False
            await cog.on_guild_role_update(NS(name="New", position=1), NS(name="New", position=2, guild=guild))
            self.assertTrue(cog._full_pending)
            cog._full_pending = False
            await cog.on_guild_role_delete(NS(guild=guild))
            self.assertTrue(cog._full_pending)

    async def test_paging_even_with_lower_server_cap(self):
        cog = self.make_cog({i: None for i in range(8)}, [])
        self.db.cap = 3
        with patch.object(positions, "PAGE_SIZE", 4):
            result = await cog.reconcile_all()
        self.assertEqual(result.examined, 8)
        self.assertEqual([page[0] for page in self.db.pages], [0, 3, 6, 8])

    async def test_individual_unregistered_and_departed(self):
        cog = self.make_cog({1: "Intern"}, [])
        await cog._reconcile_member(99)
        self.assertEqual(self.db.writes, [])
        await cog._reconcile_member(1)
        self.assertIsNone(self.db.rows[1]["position"])

    async def test_write_failure_is_counted_and_remaining_rows_continue(self):
        cog = self.make_cog({1: "old", 2: "old"}, [member(1, "Intern"), member(2, "Intern")])
        self.db.fail_ids.add(1)
        with self.assertLogs("cogs.positions", level="ERROR"):
            result = await cog.reconcile_all()
        self.assertEqual((result.failed, result.changed), (1, 1))
        self.assertEqual(self.db.rows[2]["position"], "Intern")

    async def test_runtime_permission_guard_and_ephemeral_report(self):
        cog = self.make_cog({}, [])
        interaction = NS(guild_id=positions.GUILD_ID, permissions=NS(manage_guild=False),
                         response=NS(send_message=AsyncMock(), defer=AsyncMock()), followup=NS(send=AsyncMock()))
        await Positions.syncpositions.callback(cog, interaction)
        interaction.response.send_message.assert_awaited_once()
        interaction.response.defer.assert_not_awaited()
        interaction.permissions.manage_guild = True
        interaction.guild_id = None
        await Positions.syncpositions.callback(cog, interaction)
        self.assertEqual(self.guild.scans, 0)
        interaction.guild_id = positions.GUILD_ID
        await Positions.syncpositions.callback(cog, interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        self.assertIn("examined: 0", interaction.followup.send.await_args.args[0])
        self.assertTrue(interaction.followup.send.await_args.kwargs["ephemeral"])

    async def test_coalesced_full_requests_and_cleanup(self):
        cog = self.make_cog({}, [])
        cog.queue_full()
        cog.queue_full()
        await cog._worker
        self.assertEqual(self.guild.scans, 1)
        cog.queue_full()
        await cog.cog_unload()
        self.assertTrue(cog._worker.cancelled())

    def test_registration_hook_failure_does_not_escape(self):
        bot = NS(get_cog=lambda name: NS(queue_member=lambda uid: (_ for _ in ()).throw(RuntimeError("boom"))))
        with self.assertLogs("position_utils", level="ERROR"):
            schedule_position_sync(bot, 1)


if __name__ == "__main__":
    unittest.main()
