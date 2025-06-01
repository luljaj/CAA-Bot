from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests
import json

GUILD_ID = int(os.getenv("GUILDID"))


class Editevents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase
    @app_commands.command(
        name="editevents",
        description="Change an employee's event win count."
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.default_permissions(manage_events=True)  
    @app_commands.guilds(Object(id=GUILD_ID)) 


    async def editevents(self, interaction: Interaction, user: discord.User, wincount: int):
        self.user = user
        if 0 > wincount > 999:
            await interaction.response.send_message(f'Win count invalid.', ephemeral=True)
            return None
        response =  (
            self.supabase.rpc("editevent", params = {"edit_val":wincount,"uid":self.user.id})
            .execute()
            )
        
        await interaction.response.send_message(f'{user.mention}\'s event win count is now {wincount}.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(Editevents(bot))
