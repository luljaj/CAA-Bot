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


class Eventwinner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    @app_commands.command(
        name="eventwinner",
        description="Give an employee their win credentials."
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID)) 


    async def eventwinner(self, interaction: Interaction, user: discord.User):
        self.user = user
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()

            cursor.execute("UPDATE stats SET eventswon = eventswon + 1 WHERE discordid = ?", (user.id,))

        ewin = discord.utils.get(interaction.guild.roles, name="Event Winner")
        await self.user.add_roles(ewin, reason = f'Event win given by <@{interaction.user.id}>')


        await interaction.response.send_message(f'{user.mention}\'s has been awarded for their event win and given the role.', ephemeral=True)








async def setup(bot):
    await bot.add_cog(Eventwinner(bot))
