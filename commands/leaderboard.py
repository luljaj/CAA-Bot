import os

import discord
from discord import Interaction, Object, app_commands
from discord.ext import commands

from application_utils import execute_supabase
from config import SERVER_ICON


GUILD_ID = int(os.getenv("GUILDID"))


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="leaderboard",
        description="View the top 10 report answerers.",
    )
    @app_commands.guilds(Object(id=GUILD_ID))
    async def leaderboard(self, interaction: Interaction):
        await interaction.response.defer(thinking=True)

        response = await execute_supabase(self.supabase.rpc("top_reports"))
        entries = (response.data or [])[:10]

        if not entries:
            await interaction.followup.send(
                "No report data found.",
                ephemeral=True,
            )
            return

        medals = ["🥇", "🥈", "🥉"]
        board = "\n".join(
            f"{medals[rank - 1] if rank <= 3 else f'#{rank}'} "
            f"{entry.get('username') or 'Unknown'} — "
            f"**{entry.get('reports_answered', 0) or 0}**"
            for rank, entry in enumerate(entries, start=1)
        )

        embed = discord.Embed(
            title="🏆 REPORTS LEADERBOARD",
            description=board,
            color=discord.Color.gold(),
        )
        embed.set_footer(
            text="Custom Adversaries Association",
            icon_url=SERVER_ICON,
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
