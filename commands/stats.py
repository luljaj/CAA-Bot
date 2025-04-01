from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests

# Environment and config
db_folder = './databases'
db_file = os.path.join(db_folder, 'database.db')
GUILD_ID = int(os.getenv("GUILDID"))
REVIEW_CHANNEL = 1356017239039414615


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="stats",
        description="Retrieve a users stats."
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID)) 
    async def stats(self, interaction: Interaction, user: discord.User):
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, cash, reports, eventswon FROM stats WHERE discordid = ?",
                (user.id,)
            )
            row = cursor.fetchone()

        if not row:
            await interaction.response.send_message(
                f"No stats found for {user.mention}.",
                ephemeral=True
            )
            return

        username, cash, reports, eventswon = row

        avatar_url = user.avatar.url

        embed = discord.Embed(
            title="📊 Profile",
            description=f"{user.mention}'s CAA Profile",
            color=discord.Color.dark_grey()
        )
        embed.add_field(name="Roblox Username", value=username, inline=True)
        embed.add_field(name="Cash", value=cash, inline=False)
        embed.add_field(name="Reports", value=reports, inline=False)
        embed.add_field(name="Events Won", value=eventswon, inline=False)
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text = 'Custom Adversaries Association', icon_url='https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024')

        await interaction.response.send_message(embed=embed)








async def setup(bot):
    await bot.add_cog(Stats(bot))
