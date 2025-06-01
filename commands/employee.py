from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests
import json

GUILD_ID = int(os.getenv("GUILDID"))


class Employee(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase
    @app_commands.command(
        name="employee",
        description="Upgrade an intern to employee."
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID)) 


    async def employee(self, interaction: Interaction, user: discord.User):
        self.user = user

        employee = discord.utils.get(interaction.guild.roles, name="Event Winner")
        await self.user.add_roles(employee, reason = f'Employee promoted by <@{interaction.user.id}>')


        await interaction.response.send_message(f'{user.mention}\'s has been promoted to Employee.', ephemeral=True)
        
async def setup(bot):
    await bot.add_cog(Employee(bot))
