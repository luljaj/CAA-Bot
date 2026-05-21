from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

from config import SERVER_ICON

GUILD_ID = int(os.getenv("GUILDID"))

RPC_MAP = {
    "points": "top_points",
    "income": "top_donations",
    "referrals": "top_recruitment",
    "eventwins": "top_events",
    "reports": "top_reports",
}

LABEL_MAP = {
    "points": "POINTS",
    "income": "INCOME",
    "referrals": "REFERRALS",
    "eventwins": "EVENT WINS",
    "reports": "REPORTS",
}

# (id_key, value_key) for each category's RPC return schema
FIELD_MAP = {
    "points":    ("discordid", "points"),
    "income":    ("discordid", "donations"),
    "referrals": ("inviter_id", "invite_count"),
    "eventwins": ("discordid", "eventswon"),
    "reports":   ("discordid", "reports_answered"),
}


class Podium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="podium",
        description="View the top 3 in a category."
    )
    @app_commands.describe(category="The category to rank by.")
    @app_commands.choices(category=[
        app_commands.Choice(name="Points", value="points"),
        app_commands.Choice(name="Income", value="income"),
        app_commands.Choice(name="Referrals", value="referrals"),
        app_commands.Choice(name="Event Wins", value="eventwins"),
        app_commands.Choice(name="Reports", value="reports"),
    ])
    @app_commands.guilds(Object(id=GUILD_ID))
    async def podium(self, interaction: Interaction, category: str):
        await interaction.response.defer(thinking=True)

        rpc_name = RPC_MAP[category]
        response = self.supabase.rpc(rpc_name).execute()

        label = LABEL_MAP[category]

        if not response.data:
            await interaction.followup.send(f"No data found for {label}.", ephemeral=True)
            return

        entries = response.data
        id_key, value_key = FIELD_MAP[category]
        board = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, entry in enumerate(entries[:3]):
            username = entry.get("username", "Unknown")
            value = entry.get(value_key, 0)
            board += f"{medals[i]} {username} — **{value}**\n"

        embed = discord.Embed(
            title=f"🏆 {label} PODIUM",
            description=board,
            color=discord.Color.gold()
        )
        embed.set_footer(
            text='Custom Adversaries Association',
            icon_url=SERVER_ICON
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Podium(bot))
