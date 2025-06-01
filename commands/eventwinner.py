from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests
import json

GUILD_ID = int(os.getenv("GUILDID"))


class Eventwinner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase
    @app_commands.command(
        name="eventwinner",
        description="Give an employee their win credentials."
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.default_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID)) 


    async def eventwinner(self, interaction: Interaction, user: discord.User):
        self.user = user
        response =  (
            self.supabase.rpc("addevent", params = {"uid":self.user.id})
            .execute()
            )

        ewin = discord.utils.get(interaction.guild.roles, name="Event Winner")
        await self.user.add_roles(ewin, reason = f'Event win given by <@{interaction.user.id}>')


        await interaction.response.send_message(f'{user.mention}\'s has been awarded for their event win and given the role.', ephemeral=True)
        
async def setup(bot):
    await bot.add_cog(Eventwinner(bot))
