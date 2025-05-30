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


class Refile(commands.Cog):
    def __init__(self, bot, supabase):
        self.bot = bot
        self.supabase = supabase
    @app_commands.command(
        name="refile",
        description="Recreate an employee's file."
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID)) 


    async def refile(self, interaction: Interaction, user: discord.User, robloxuser: str):
        self.user = user
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            REPLACE INTO stats (discordid, username)
            VALUES (?, ?)
            ''', (
                self.user.id,
                robloxuser,
            ))
        await interaction.response.send_message(f'{user.mention}\'s file has been recreated.', ephemeral=True)








async def setup(bot):
    await bot.add_cog(Refile(bot))
