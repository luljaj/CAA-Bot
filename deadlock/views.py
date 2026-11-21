from contextlib import suppress
from dataclasses import dataclass
import logging

import aiohttp
import discord

from application_utils import execute_supabase
from deadlock.client import API_ERRORS, api_error_message, fallback_profile
from deadlock.embeds import build_match_embed, build_player_embed
from deadlock.ids import MAX_ACCOUNT_ID, account_id, steam_id64

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmployeeRecord:
    embed: discord.Embed
    steam_id: int


async def _find_caa_players(supabase, guild, players: list[dict]) -> dict[int, discord.Member]:
    account_ids = {player.get("account_id") for player in players}
    steam_ids = [
        steam_id64(player_id)
        for player_id in account_ids
        if isinstance(player_id, int) and 0 < player_id <= MAX_ACCOUNT_ID
    ]
    if not steam_ids or guild is None:
        return {}
    try:
        response = await execute_supabase(
            supabase.table("stats").select("discordid,steam_id").in_("steam_id", steam_ids)
        )
    except Exception:
        logger.exception("Could not look up linked CAA members for a Deadlock match")
        return {}

    members = {}
    for row in response.data or []:
        if row["discordid"] is not None:
            member = guild.get_member(int(row["discordid"]))
            if member is not None:
                members[account_id(int(row["steam_id"]))] = member
    return members


def _guild_icon_url(guild) -> str | None:
    icon = getattr(guild, "icon", None)
    return icon.url if icon else None


async def show_linked_record(
    interaction: discord.Interaction, client, supabase, employee_record: EmployeeRecord
):
    steam_id = int(employee_record.steam_id)
    try:
        profile = await client.lookup_steam_profile(steam_id) or fallback_profile(steam_id)
        player_data = await client.get_player_data(profile)
    except API_ERRORS as error:
        await interaction.followup.send(api_error_message(error), ephemeral=True)
        return

    embed, recent = build_player_embed(
        profile, *player_data, footer_icon=_guild_icon_url(getattr(interaction, "guild", None))
    )
    await interaction.edit_original_response(
        embed=embed,
        view=DeadlockRecordView(client, supabase, recent, employee_record),
    )


async def show_match(interaction: discord.Interaction, client, supabase, match_id: int):
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        match, heroes = await client.get_match_data(match_id)
    except API_ERRORS as error:
        if isinstance(error, aiohttp.ClientResponseError) and error.status == 404:
            message = f"No Deadlock match found for `#{match_id}`."
        else:
            message = api_error_message(error)
        await interaction.edit_original_response(content=message)
        return

    caa_players = await _find_caa_players(supabase, interaction.guild, match["players"])
    embed = build_match_embed(
        match_id, match, heroes, caa_players, footer_icon=_guild_icon_url(interaction.guild)
    )
    # Finish the private acknowledgement so the public card is a new message.
    await interaction.edit_original_response(content=f"Opened match `#{match_id}`.")
    await interaction.followup.send(
        embed=embed,
        ephemeral=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    with suppress(discord.NotFound):
        await interaction.delete_original_response()


class EmployeeRecordView(discord.ui.View):
    def __init__(self, client, supabase, record: EmployeeRecord):
        super().__init__(timeout=900)
        self.client = client
        self.supabase = supabase
        self.record = record

    @discord.ui.button(label="View Deadlock Stats", style=discord.ButtonStyle.primary)
    async def open_deadlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await show_linked_record(interaction, self.client, self.supabase, self.record)


class DeadlockRecordView(discord.ui.View):
    def __init__(self, client, supabase, recent, employee_record: EmployeeRecord | None = None):
        super().__init__(timeout=900)
        self.client = client
        self.supabase = supabase
        self.employee_record = employee_record
        if recent:
            matches = discord.ui.Select(
                placeholder="Open a recent match",
                options=[
                    discord.SelectOption(
                        label=f"#{match.match_id} · {match.hero}"[:100],
                        description=f"{match.outcome} · {match.kda} K/D/A" + (" · MVP" if match.mvp else ""),
                        value=str(match.match_id),
                    )
                    for match in recent
                ],
            )
            matches.callback = self.open_match
            self.add_item(matches)
            self.matches = matches
        if employee_record is not None:
            back = discord.ui.Button(label="View Employee Record", style=discord.ButtonStyle.secondary)
            back.callback = self.open_employee_record
            self.add_item(back)

    async def open_match(self, interaction: discord.Interaction):
        await show_match(interaction, self.client, self.supabase, int(self.matches.values[0]))

    async def open_employee_record(self, interaction: discord.Interaction):
        record = self.employee_record
        await interaction.response.edit_message(
            embed=record.embed,
            view=EmployeeRecordView(self.client, self.supabase, record),
        )
