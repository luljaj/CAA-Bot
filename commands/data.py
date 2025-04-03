from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests
import json

# Environment and config
db_folder = './databases'
db_file = os.path.join(db_folder, 'database.db')
GUILD_ID = int(os.getenv("GUILDID"))
REVIEW_CHANNEL = 1356017239039414615


class Data(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="data",
        description="Edit a users data. (DO NOT USE IF YOU DO NOT UNDERSTAND.)"
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID)) 
    async def data(self, interaction: Interaction, user: discord.User, award: str):
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT awards FROM stats WHERE discordid = ?", (user.id,))
            row = cursor.fetchone()
            awards = json.loads(row[0]) if row and row[0] else []
            if award[0] == "-":
                try:
                    awards.remove(award[1:])
                except:
                    None
            if award == "clearawards":
                awards.clear()
            else:
                awards.append(award)

            cursor.execute("UPDATE stats SET awards = ? WHERE discordid = ?", (json.dumps(awards), user.id))

        if not row:
            await interaction.response.send_message(
                f"No stats found for {user.mention}.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(f'{user.mention} awarded with \'{award}\'.')








async def setup(bot):
    await bot.add_cog(Data(bot))
