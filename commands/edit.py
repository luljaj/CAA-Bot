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


class Edit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    @app_commands.command(
        name="edit",
        description="Edit an employee's file."
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID)) 
    @app_commands.choices(slot = [app_commands.Choice(name = 'Username', value = 'username'),
            app_commands.Choice(name = 'Events Won', value = 'eventswon')])


    async def edit(self, interaction: Interaction, user: discord.User, slot: app_commands.Choice[str], val: str):
        value = None
        if slot.value in ['eventswon']:
            try:
                value = int(val)
            except:
                await interaction.response.send_message(f'{slot.name} must be reported as a number.', ephemeral=True)
                return
        else:
            value = val
            
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE stats SET {slot.value} = ? WHERE discordid = ?", (value, user.id))
            conn.commit()

        await interaction.response.send_message(f'{user.mention}\'s {slot.value} has been changed to {value}.', ephemeral=True)

async def setup(bot):
    await bot.add_cog(Edit(bot))
