from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

GUILD_ID = int(os.getenv("GUILDID"))

RPC_MAP = {
    "points": "top_points",
    "income": "top_donations",
    "referrals": "top_recruitment",
    "eventwins": "top_events",
}

LABEL_MAP = {
    "points": "POINTS",
    "income": "INCOME",
    "referrals": "REFERRALS",
    "eventwins": "EVENT WINS",
}

# (id_key, value_key) for each category's RPC return schema
FIELD_MAP = {
    "points":   ("discordid", "points"),
    "income":   ("discordid", "donations"),
    "referrals":("inviter_id", "invite_count"),
    "eventwins":("discordid", "eventswon"),
}


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="leaderboard",
        description="View the top 5 in a category."
    )
    @app_commands.describe(category="The category to rank by.")
    @app_commands.choices(category=[
        app_commands.Choice(name="Points", value="points"),
        app_commands.Choice(name="Income", value="income"),
        app_commands.Choice(name="Referrals", value="referrals"),
        app_commands.Choice(name="Event Wins", value="eventwins"),
    ])
    @app_commands.guilds(Object(id=GUILD_ID))
    async def leaderboard(self, interaction: Interaction, category: str):
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
            discordid = entry.get(id_key)
            value = entry.get(value_key, 0)
            board += f"{medals[i]} <@{discordid}> — **{value}**\n"

        embed = discord.Embed(
            title=f"📊 {label} LEADERBOARD",
            description=board,
            color=discord.Color.gold()
        )
        embed.set_footer(
            text='Custom Adversaries Association',
            icon_url='https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024'
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
