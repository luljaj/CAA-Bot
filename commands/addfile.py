from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests
import json

GUILD_ID = int(os.getenv("GUILDID"))


class Addfile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase
    @app_commands.command(
        name="addfile",
        description="Add a person to the database if they are not in already."
    )
    @app_commands.default_permissions(manage_events=True)  
    @app_commands.guilds(Object(id=GUILD_ID)) 


    async def addfile(self, interaction: Interaction, user: discord.User):
        self.user = user
        response =  (
            self.supabase.rpc("register", params = {"uid":self.user.id, "u" :self.user.display_name, "r":"Unknown", "inv":"Unknown"})
            .execute()
            )
        
        await interaction.response.send_message(f'{user.mention} has been registered to the database as {self.user.display_name}.')


async def setup(bot):
    await bot.add_cog(Addfile(bot))
