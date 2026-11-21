import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

os.environ.setdefault("GUILDID", "123")

from commands import match as match_command
from commands import stats as stats_command
from commands import steam_link as steam_link_command
from deadlock.embeds import build_match_embed, build_player_embed, display_name
from deadlock.ids import STEAM_ID64_BASE, account_id, parse_steam_reference, steam_id64
from deadlock.views import DeadlockRecordView, EmployeeRecord, EmployeeRecordView, show_linked_record


class DeadlockIdsTests(unittest.TestCase):
    def test_steam_id_conversions(self):
        friend_code = 12345678
        id64 = STEAM_ID64_BASE + friend_code
        self.assertEqual(steam_id64(friend_code), id64)
        self.assertEqual(steam_id64(id64), id64)
        self.assertEqual(account_id(id64), friend_code)
        self.assertEqual(account_id(friend_code), friend_code)

        with self.assertRaises(ValueError):
            steam_id64(0)
        with self.assertRaises(ValueError):
            steam_id64(STEAM_ID64_BASE)

    def test_parse_steam_reference(self):
        friend_code = 424242
        id64 = STEAM_ID64_BASE + friend_code

        self.assertEqual(parse_steam_reference(str(friend_code)), id64)
        self.assertEqual(parse_steam_reference(f"<{id64}>"), id64)
        self.assertEqual(parse_steam_reference(f"https://steamcommunity.com/profiles/{id64}/"), id64)
        self.assertEqual(parse_steam_reference("steamcommunity.com/id/my_vanity-1/"), "my_vanity-1")

        for bad in ("https://example.com/profiles/76561197960265729", "steamcommunity.com/groups/caa", "not-a-link"):
            with self.assertRaises(ValueError):
                parse_steam_reference(bad)


class DeadlockEmbedsTests(unittest.TestCase):
    def test_display_name_escapes_markdown_and_falls_back(self):
        self.assertEqual(display_name({"personaname": "*Agent_1*"}), r"\*Agent\_1\*")
        self.assertEqual(display_name({"personaname": ""}), "Steam player")

    def test_build_player_embed_and_recent_matches(self):
        profile = {
            "account_id": 100,
            "personaname": "Tester",
            "profileurl": "https://steamcommunity.com/profiles/76561197960265828",
            "avatarfull": "https://example.com/avatar.png",
        }
        matches = [
            {
                "match_id": 999,
                "hero_id": 1,
                "player_match_outcome": 1,
                "player_kills": 10,
                "player_deaths": 2,
                "player_assists": 8,
                "start_time": 1700000000,
            },
            {
                "match_id": 998,
                "hero_id": 1,
                "player_match_outcome": 2,
                "player_kills": 3,
                "player_deaths": 5,
                "player_assists": 4,
                "start_time": 1699990000,
            },
        ]
        embed, recent = build_player_embed(
            profile,
            matches,
            heroes={1: "Abrams"},
            ranks={3: {"name": "Phantom", "color": "#112233"}},
            rank={"rank": 3, "subrank": 2},
            mvp_matches={999},
        )
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields["RANK"], "Phantom 2")
        self.assertEqual(fields["WIN RATE"], "50.0%")
        self.assertEqual(len(recent), 2)
        self.assertTrue(recent[0].mvp)
        self.assertIn("**MVP**", recent[0].summary)

    def test_build_match_embed_mentions_caa_members(self):
        member = SimpleNamespace(mention="<@55>")
        match = {
            "start_time": 1700000000,
            "duration_s": 1805,
            "match_outcome": 0,
            "winning_team": 0,
            "players": [
                {"account_id": 100, "team": 0, "hero_id": 1, "kills": 9, "deaths": 1, "assists": 7, "mvp_rank": 1},
                {"account_id": 200, "team": 1, "hero_id": 2, "kills": 2, "deaths": 6, "assists": 3, "mvp_rank": 2},
            ],
        }
        embed = build_match_embed(777, match, heroes={1: "Abrams", 2: "Haze"}, caa_players={100: member})
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields["DURATION"], "30:05")
        self.assertIn("TEAM 1 · WINNER", fields)
        self.assertIn("<@55>", fields["TEAM 1 · WINNER"])
        self.assertIn("**MVP**", fields["TEAM 1 · WINNER"])


class StatsSteamLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_roblox_avatar_lookup_does_not_clobber_steam_id(self):
        steam_id = STEAM_ID64_BASE + 555
        stats_row = {
            "id": 7,
            "discordid": 42,
            "username": "RobloxUser",
            "eventswon": 3,
            "awards": ["Medal"],
            "reports_answered": 2,
            "steam_id": steam_id,
        }

        supabase = MagicMock()
        def rpc_side_effect(name, params):
            query = MagicMock()
            if name == "fetchstats":
                query.execute.return_value = SimpleNamespace(data=stats_row)
            else:
                query.execute.return_value = SimpleNamespace(data=[{"invite_count": 1}])
            return query

        supabase.rpc.side_effect = rpc_side_effect
        bot = SimpleNamespace(supabase=supabase, deadlock=object())
        cog = stats_command.Stats(bot)

        role = SimpleNamespace(name="Employee", color=discord.Color.blue())
        user = SimpleNamespace(
            id=42,
            name="Agent",
            mention="<@42>",
            avatar=SimpleNamespace(url="https://example.com/discord.png"),
            default_avatar=SimpleNamespace(url="https://example.com/default.png"),
            roles=[role],
            guild=SimpleNamespace(default_role=role),
        )
        interaction = SimpleNamespace(
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )

        avatar_response = AsyncMock()
        avatar_response.json = AsyncMock(return_value={"data": [{"imageUrl": "https://example.com/roblox.png"}]})
        avatar_cm = AsyncMock()
        avatar_cm.__aenter__.return_value = avatar_response
        session = MagicMock()
        session.get.return_value = avatar_cm
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session

        with (
            patch.object(stats_command, "getUserId", AsyncMock(return_value="99999")),
            patch.object(stats_command.aiohttp, "ClientSession", return_value=session_cm),
        ):
            await cog.stats.callback(cog, interaction, user)

        # Steam ID came straight from fetchstats without falling back to a table query.
        supabase.table.assert_not_called()
        send_kwargs = interaction.followup.send.await_args.kwargs
        self.assertIsInstance(send_kwargs["view"], EmployeeRecordView)
        self.assertEqual(send_kwargs["view"].record, EmployeeRecord(send_kwargs["embed"], steam_id))
        self.assertEqual(send_kwargs["embed"].thumbnail.url, "https://example.com/roblox.png")


class DeadlockCommandAndViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_match_command_posts_scoreboard_and_mentions_other_caa_members(self):
        caller = SimpleNamespace(id=10, mention="<@10>")
        teammate = SimpleNamespace(id=20, mention="<@20>")
        guild = SimpleNamespace(get_member=lambda uid: {10: caller, 20: teammate}.get(uid))

        client = SimpleNamespace(
            get_match_data=AsyncMock(
                return_value=(
                    {
                        "start_time": 1700000000,
                        "duration_s": 900,
                        "match_outcome": 0,
                        "winning_team": 0,
                        "players": [
                            {"account_id": 100, "team": 0, "hero_id": 1, "kills": 5, "deaths": 1, "assists": 4, "mvp_rank": 1},
                            {"account_id": 200, "team": 0, "hero_id": 2, "kills": 4, "deaths": 2, "assists": 6, "mvp_rank": 2},
                        ],
                    },
                    {1: "Abrams", 2: "Haze"},
                )
            )
        )
        supabase = MagicMock()
        supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = SimpleNamespace(
            data=[
                {"discordid": 10, "steam_id": STEAM_ID64_BASE + 100},
                {"discordid": 20, "steam_id": STEAM_ID64_BASE + 200},
            ]
        )

        cog = match_command.Match(SimpleNamespace(deadlock=client, supabase=supabase))
        interaction = SimpleNamespace(
            user=caller,
            guild=guild,
            response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
            edit_original_response=AsyncMock(),
            followup=SimpleNamespace(send=AsyncMock()),
            delete_original_response=AsyncMock(),
        )

        await cog.match.callback(cog, interaction, 0)
        interaction.response.send_message.assert_awaited_once()

        await cog.match.callback(cog, interaction, 555)
        send_kwargs = interaction.followup.send.await_args.kwargs
        self.assertEqual(send_kwargs["content"], "CAA members in this match · <@20>")
        self.assertFalse(send_kwargs["ephemeral"])
        self.assertEqual(send_kwargs["embed"].title, "📂 DEADLOCK MATCH #555")

    async def test_steam_link_uses_bot_client_and_service_supabase(self):
        steam_id = STEAM_ID64_BASE + 777
        client = SimpleNamespace(
            lookup_steam_profile=AsyncMock(
                return_value={
                    "account_id": 777,
                    "personaname": "LinkedUser",
                    "profileurl": f"https://steamcommunity.com/profiles/{steam_id}",
                    "avatarfull": None,
                }
            )
        )
        service_supabase = MagicMock()
        bot = SimpleNamespace(deadlock=client, supabase=MagicMock(), service_supabase=service_supabase)
        cog = steam_link_command.SteamLink(bot)
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=42),
            response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
            edit_original_response=AsyncMock(),
        )

        await cog.steam_link.callback(cog, interaction, "777")
        client.lookup_steam_profile.assert_awaited_once_with(steam_id, refresh_missing=True)
        kwargs = interaction.edit_original_response.await_args.kwargs
        self.assertIsInstance(kwargs["view"], steam_link_command.ConfirmSteamLink)
        self.assertIs(kwargs["view"].supabase, service_supabase)

    async def test_linked_record_round_trips_back_to_employee_record(self):
        steam_id = STEAM_ID64_BASE + 321
        employee_embed = discord.Embed(title="Employee")
        record = EmployeeRecord(employee_embed, steam_id)
        client = SimpleNamespace(
            lookup_steam_profile=AsyncMock(return_value=None),
            get_player_data=AsyncMock(return_value=([], {}, {}, None, set())),
        )
        supabase = MagicMock()
        interaction = SimpleNamespace(
            edit_original_response=AsyncMock(),
            followup=SimpleNamespace(send=AsyncMock()),
            response=SimpleNamespace(edit_message=AsyncMock()),
        )

        await show_linked_record(interaction, client, supabase, record)
        view = interaction.edit_original_response.await_args.kwargs["view"]
        self.assertIsInstance(view, DeadlockRecordView)

        await view.open_employee_record(interaction)
        back_kwargs = interaction.response.edit_message.await_args.kwargs
        self.assertIs(back_kwargs["embed"], employee_embed)
        self.assertIsInstance(back_kwargs["view"], EmployeeRecordView)
        self.assertEqual(back_kwargs["view"].record, record)
