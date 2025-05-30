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


class Award(commands.Cog):
    def __init__(self, bot, supabase):
        self.bot = bot
        self.supabase = supabase

    @app_commands.command(
        name="award",
        description="Give a user an award."
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID)) 
    async def award(self, interaction: Interaction, user: discord.User, award: str):
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT awards FROM stats WHERE discordid = ?", (user.id,))
            row = cursor.fetchone()
            awards = json.loads(row[0]) if row and row[0] else []
            if award[0] == "-":
                proc = 0
                try:
                    awards.remove(award[1:]) 
                except:
                    None
            elif award == "clearawards":
                proc = 1
                awards.clear()
            else:
                proc = 2
                awards.append(award)

            cursor.execute("UPDATE stats SET awards = ? WHERE discordid = ?", (json.dumps(awards), user.id))

        if not row:
            await interaction.response.send_message(
                f"No stats found for {user.mention}.",
                ephemeral=True
            )
            return

        if proc == 0:
            await interaction.response.send_message(f'Award \'{award[1:]}\' removed from {user.mention}.', ephemeral= True)
        elif proc == 1:
            await interaction.response.send_message(f'{user.mention} awards have been cleared.', ephemeral= True)
        elif proc == 2:
            await interaction.response.send_message(f'{user.mention} awarded with \'{award}\'.', ephemeral= True)









async def setup(bot):
    await bot.add_cog(Award(bot))
