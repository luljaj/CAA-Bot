from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests
import json

GUILD_ID = int(os.getenv("GUILDID"))


class Setalias(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase
    @app_commands.command(
        name="setalias",
        description="Change an employee's alias on file."
    )
    @app_commands.checks.has_permissions(manage_events=True) 
    @app_commands.default_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID)) 


    async def setalias(self, interaction: Interaction, user: discord.User, robloxuser: str):
        self.user = user
        self.robloxuser = robloxuser

        if len(robloxuser) > 50 or not robloxuser.isalnum():
            await interaction.response.send_message(f'Invalid alias.', ephemeral=True)
            return None
        response = (
                self.supabase.rpc("setalias", params = {"uid": self.user.id, "u" : robloxuser})
                .execute()
            )
        
        print(response)

        await self.user.edit(nick=self.robloxuser)

        await interaction.response.send_message(f'{user.mention}\'s alias has been updated to {self.robloxuser}.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(Setalias(bot))
