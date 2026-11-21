import asyncio
from collections import Counter
import os
from time import monotonic

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config import SERVER_ICON

GUILD_ID = int(os.getenv("GUILDID"))
DEADLOCK_API = "https://api.deadlock-api.com/v1"
API_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError)
MATCH_OUTCOMES = {
    1: "Win",
    2: "Loss",
    3: "Penalized",
    4: "Party penalty",
    5: "Unscored",
}


def _api_session():
    headers = {"Accept": "application/json", "User-Agent": "CAA-Bot/1.0"}
    api_key = os.getenv("DEADLOCK_API_KEY")
    if api_key:
        headers["X-API-KEY"] = api_key
    return aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=12), raise_for_status=True
    )


async def _get_json(session, path, *, params=None, expected=list):
    async with session.get(f"{DEADLOCK_API}/{path}", params=params, allow_redirects=False) as response:
        payload = await response.json()
    if not isinstance(payload, expected):
        raise ValueError("Unexpected Deadlock API response")
    return payload


async def _get_optional_json(session, path, *, expected=list):
    try:
        return await _get_json(session, path, expected=expected)
    except API_ERRORS:
        return None


def _api_error_message(error):
    if isinstance(error, aiohttp.ClientResponseError) and error.status == 429:
        return "The Deadlock API is rate-limiting requests. Try again shortly."
    return "The Deadlock API is temporarily unavailable. Try again shortly."


def _display_name(profile):
    return discord.utils.escape_markdown(profile["personaname"] or "Steam player")


def _build_embed(profile, history, heroes, ranks, rank):
    matches = sorted(history, key=lambda match: match["start_time"], reverse=True)
    outcomes = Counter(match["player_match_outcome"] for match in matches)
    wins, losses = outcomes[1], outcomes[2]
    decided_matches = wins + losses
    win_rate = f"{wins / decided_matches:.1%}" if decided_matches else "—"
    hero_counts = Counter(match["hero_id"] for match in matches if match["hero_id"] > 0)
    mains = [
        f"**{heroes.get(hero_id, f'Hero #{hero_id}')}** · {count} played"
        for hero_id, count in hero_counts.most_common(3)
    ]

    recent = []
    for match in matches[:5]:
        hero_id = match["hero_id"]
        hero = heroes.get(hero_id, f"Hero #{hero_id}")
        outcome = MATCH_OUTCOMES.get(match["player_match_outcome"], "Unknown result")
        kda = f"{match['player_kills']}/{match['player_deaths']}/{match['player_assists']}"
        recent.append(
            f"<t:{match['start_time']}:R> · **{outcome}** · {hero} · "
            f"`{kda}` · `#{match['match_id']}`"
        )

    tier = rank.get("rank") if rank else None
    rank_asset = ranks.get(tier, {})
    rank_name = "Unavailable"
    if tier == 0:
        rank_name = "Unranked"
    elif tier is not None:
        rank_name = rank_asset.get("name") or f"Tier {tier}"
        if rank.get("subrank"):
            rank_name += f" {rank['subrank']}"

    embed = discord.Embed(
        title=f"📂 {_display_name(profile)} - DEADLOCK RECORD",
        url=profile["profileurl"],
        color=discord.Color.from_str(rank_asset.get("color") or "#5865F2"),
    )
    embed.add_field(name=f"ROLODEX ENTRY #{profile['account_id']}", value="\u200b", inline=False)
    embed.add_field(name="RANK", value=rank_name, inline=True)
    embed.add_field(name="RECORDED MATCHES", value=len(matches), inline=True)
    embed.add_field(name="PERFORMANCE FILE", value="\u200b", inline=False)
    embed.add_field(name="WINS", value=wins, inline=True)
    embed.add_field(name="LOSSES", value=losses, inline=True)
    embed.add_field(name="WIN RATE", value=win_rate, inline=True)
    embed.add_field(name="MOST PLAYED HEROES", value="\n".join(mains) or "No heroes recorded.", inline=False)
    embed.add_field(
        name="RECENT MATCHES (K/D/A)",
        value="\n".join(recent) or "No matches recorded.",
        inline=False,
    )
    if profile["avatarfull"]:
        embed.set_thumbnail(url=profile["avatarfull"])
    embed.set_footer(text="Custom Adversaries Association", icon_url=SERVER_ICON)
    return embed


class SteamProfilePicker(discord.ui.View):
    def __init__(self, original, profiles, show_stats):
        super().__init__(timeout=90)
        self.original = original
        self.profiles = {str(profile["account_id"]): profile for profile in profiles}
        self.show_stats = show_stats
        self.choose_profile.options = [
            discord.SelectOption(
                label=f"{number}. {profile['personaname'] or 'Steam player'}"[:100],
                description=f"Account #{account_id}",
                value=account_id,
            )
            for number, (account_id, profile) in enumerate(self.profiles.items(), start=1)
        ]

    async def interaction_check(self, interaction):
        if interaction.user.id == self.original.user.id:
            return True
        await interaction.response.send_message("Only the person who ran the command can choose.", ephemeral=True)
        return False

    async def on_timeout(self):
        try:
            await self.original.edit_original_response(
                content="Steam profile selection expired. Run `/deadlock-stats` again.",
                view=None,
            )
        except discord.HTTPException:
            pass

    @discord.ui.select(placeholder="Select a Steam profile")
    async def choose_profile(self, interaction, select):
        if self.is_finished():
            await interaction.response.send_message("This selection is closed.", ephemeral=True)
            return
        profile = self.profiles[select.values[0]]
        self.stop()
        await interaction.response.defer()
        await self.show_stats(interaction, profile)


class DeadlockStats(commands.Cog):
    def __init__(self):
        self._heroes = {}
        self._ranks = {}
        self._assets_expire_at = 0
        self._assets_lock = asyncio.Lock()

    async def _get_assets(self, session):
        async with self._assets_lock:
            if monotonic() >= self._assets_expire_at:
                heroes, ranks = await asyncio.gather(
                    _get_optional_json(session, "assets/heroes"),
                    _get_optional_json(session, "assets/ranks"),
                )
                if heroes:
                    self._heroes = {hero["id"]: hero["name"] for hero in heroes}
                if ranks:
                    self._ranks = {rank["tier"]: rank for rank in ranks}
                self._assets_expire_at = monotonic() + (3600 if heroes and ranks else 60)
            return self._heroes, self._ranks

    async def _show_stats(self, interaction, profile):
        account_id = profile["account_id"]
        try:
            async with _api_session() as session:
                history = await _get_json(session, f"players/{account_id}/match-history")
                rank, (heroes, ranks) = await asyncio.gather(
                    _get_optional_json(session, f"players/{account_id}/rank", expected=dict),
                    self._get_assets(session),
                )
        except API_ERRORS as error:
            await interaction.edit_original_response(content=_api_error_message(error), view=None)
            return

        record = _build_embed(profile, history, heroes, ranks, rank)
        await interaction.edit_original_response(content=None, view=None, embed=record)

    @app_commands.command(
        name="deadlock-stats",
        description="Look up a Deadlock player's rank, main heroes, and recent matches.",
    )
    @app_commands.describe(steam_name="The player's Steam display name")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def deadlock_stats(self, interaction: discord.Interaction, steam_name: str):
        steam_name = steam_name.strip()
        if not steam_name:
            await interaction.response.send_message("Enter a Steam display name.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)

        try:
            async with _api_session() as session:
                profiles = await _get_json(
                    session,
                    "players/steam-search",
                    params={
                        "search_query": steam_name,
                        "limit": 8,
                        "min_matches_played_last_30d": 0,
                        "matches_played_weight": 0,
                    },
                )
        except API_ERRORS as error:
            await interaction.edit_original_response(content=_api_error_message(error))
            return

        if not profiles:
            await interaction.edit_original_response(
                content="No Deadlock profiles found. Check the player's Steam display name and try again."
            )
            return

        exact_profiles = [
            profile for profile in profiles
            if profile["personaname"].casefold() == steam_name.casefold()
        ]
        if len(exact_profiles) == 1:
            await self._show_stats(interaction, exact_profiles[0])
            return

        candidates = exact_profiles or profiles
        profile_links = "\n".join(
            f"[{number}. {_display_name(profile)}](<{profile['profileurl']}>) · `#{profile['account_id']}`"
            for number, profile in enumerate(candidates, start=1)
        )
        await interaction.edit_original_response(
            content=f"Choose a Steam profile to open its Deadlock record.\n{profile_links}",
            view=SteamProfilePicker(interaction, candidates, self._show_stats),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot):
    await bot.add_cog(DeadlockStats())
