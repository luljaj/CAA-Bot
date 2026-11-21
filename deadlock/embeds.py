from collections import Counter
from dataclasses import dataclass

import discord

from config import SERVER_ICON

MATCH_OUTCOMES = {
    1: "Win",
    2: "Loss",
    3: "Penalized",
    4: "Party penalty",
    5: "Unscored",
}
MATCH_TEAM_NAMES = {
    0: "THE HIDDEN KING",
    1: "THE ARCHMOTHER",
}


def display_name(profile: dict) -> str:
    return discord.utils.escape_markdown(profile.get("personaname") or "Steam player")


@dataclass(frozen=True)
class RecentMatch:
    match_id: int
    hero: str
    outcome: str
    kda: str
    start_time: int
    mvp: bool

    @property
    def summary(self) -> str:
        badge = " · **MVP**" if self.mvp else ""
        return (
            f"**{self.hero}** · {self.outcome} · `{self.kda}`{badge}\n"
            f"<t:{self.start_time}:R> · `#{self.match_id}`"
        )


def build_player_embed(
    profile: dict,
    matches: list[dict],
    heroes: dict[int, str],
    ranks: dict[int, dict],
    rank: dict | None,
    mvp_matches: set[int],
    *,
    footer_icon: str | None = None,
) -> tuple[discord.Embed, list[RecentMatch]]:
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
        match_id = match["match_id"]
        recent.append(RecentMatch(match_id, hero, outcome, kda, match["start_time"], match_id in mvp_matches))

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
        title=f"📂 {display_name(profile)} - DEADLOCK RECORD",
        url=profile["profileurl"],
        color=discord.Color.from_str(rank_asset.get("color") or "#5865F2"),
    )
    embed.add_field(name=f"STEAM ID #{profile['account_id']}", value="\u200b", inline=False)
    embed.add_field(name="RANK", value=rank_name, inline=True)
    embed.add_field(name="RECORDED MATCHES", value=len(matches), inline=True)
    embed.add_field(name="PERFORMANCE FILE", value="\u200b", inline=False)
    embed.add_field(name="WINS", value=wins, inline=True)
    embed.add_field(name="LOSSES", value=losses, inline=True)
    embed.add_field(name="WIN RATE", value=win_rate, inline=True)
    embed.add_field(name="MOST PLAYED HEROES", value="\n".join(mains) or "No heroes recorded.", inline=False)
    embed.add_field(
        name="RECENT MATCHES (K/D/A)",
        value="\n\n".join(match.summary for match in recent) or "No matches recorded.",
        inline=False,
    )
    if profile.get("avatarfull"):
        embed.set_thumbnail(url=profile["avatarfull"])
    embed.set_footer(text="Custom Adversaries Association", icon_url=footer_icon or SERVER_ICON)
    return embed, recent


def _player_sort_key(player: dict) -> tuple[int, int, int, int]:
    kills = player.get("kills") or 0
    deaths = player.get("deaths") or 0
    assists = player.get("assists") or 0
    return (
        1 if player.get("mvp_rank") == 1 else 0,
        kills + assists,
        kills,
        -deaths,
    )


def build_match_embed(
    match_id: int,
    match: dict,
    heroes: dict[int, str],
    caa_players: dict[int, discord.Member],
    *,
    footer_icon: str | None = None,
) -> discord.Embed:
    meta = []
    if start_time := match.get("start_time"):
        meta.append(f"<t:{start_time}:f>")
    if (duration := match.get("duration_s")) is not None:
        minutes, seconds = divmod(duration, 60)
        meta.append(f"Duration `{minutes}:{seconds:02d}`")

    embed = discord.Embed(
        title=f"📂 DEADLOCK MATCH #{match_id}",
        description=" · ".join(meta) or None,
        color=discord.Color.blurple(),
    )
    winner = match.get("winning_team") if match.get("match_outcome") in (None, 0) else None
    for team, team_name in MATCH_TEAM_NAMES.items():
        team_players = sorted(
            (player for player in match["players"] if player.get("team") == team),
            key=_player_sort_key,
            reverse=True,
        )
        scoreboard = []
        for player in team_players:
            hero_id = player.get("hero_id")
            hero = heroes.get(hero_id, f"Hero #{hero_id}" if hero_id else "Unknown hero")
            kills = player.get("kills") or 0
            deaths = player.get("deaths") or 0
            assists = player.get("assists") or 0
            kda = f"{kills:>2}/{deaths:>2}/{assists:>2}"
            member = caa_players.get(player.get("account_id"))
            mention = f" · {member.mention}" if member else ""
            badge = " · **MVP**" if player.get("mvp_rank") == 1 else ""
            scoreboard.append(f"`{kda}` **{hero}**{badge}{mention}")
        label = f"🏆 {team_name} — WINNER" if team == winner else team_name
        embed.add_field(name=label, value="\n".join(scoreboard) or "No roster available.", inline=False)
    embed.set_footer(text="Custom Adversaries Association · K/D/A", icon_url=footer_icon or SERVER_ICON)
    return embed
