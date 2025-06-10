from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests
import json

GUILD_ID = int(os.getenv("GUILDID"))


class Award(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="award",
        description="Give a user an award."
    )
    @app_commands.default_permissions(manage_events=True)  
    @app_commands.guilds(Object(id=GUILD_ID)) 
    async def award(self, interaction: Interaction, user: discord.User, award: str):
        self.user = user
        if len(award) > 50:
            await interaction.response.send_message(f'Award name is too long.', ephemeral= True)
            return
        if award[0] == "-":
            proc = 0 
            response = (
                self.supabase.rpc("removeaward", params = {"uid": self.user.id, "award": award})
                .execute()
            )
        elif award == "clearawards":
            proc = 1
            response = (
                self.supabase.rpc("clearawards", params = {"uid": self.user.id})
                .execute()
            )
        else:
            proc = 2
            response = (
                self.supabase.rpc("addaward", params = {"uid": self.user.id, "award": award})
                .execute()
            )


        if proc == 0:
            await interaction.response.send_message(f'Award \'{award[1:]}\' removed from {user.mention}.', ephemeral= True)
        elif proc == 1:
            await interaction.response.send_message(f'{user.mention} awards have been cleared.', ephemeral= True)
        elif proc == 2:
            await interaction.response.send_message(f'{user.mention} awarded with \'{award}\'.', ephemeral= True)

async def setup(bot):
    await bot.add_cog(Award(bot))
