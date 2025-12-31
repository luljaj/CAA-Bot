from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests
import json

GUILD_ID = int(os.getenv("GUILDID"))

def larnagack():
    async def predicate(interaction: Interaction) -> bool:
        if interaction.user.id != 270202464861421568:
            raise app_commands.CheckFailure("Not available for use.")
        return True
    return app_commands.check(predicate)


class Migrate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase
    @app_commands.command(
        name="migrate",
        description="Migrates the entire server over. Do not use."
    )
    @larnagack()
    @app_commands.default_permissions(manage_events=True)  
    @app_commands.guilds(Object(id=GUILD_ID)) 

    async def Migrate(self, interaction: Interaction):

        print('STARTING MIGRATION')

        self.guild = await self.bot.fetch_guild(GUILD_ID)
        members = [m async for m in self.guild.fetch_members(limit=None)]

        def SortMembers(members):

            members = sorted(members, key=lambda m: m.joined_at or m.created_at)
            smembers = []

            for i in members:
                if i.bot or len(i.roles) < 1:
                    print('Did not pass to smembers..')
                    continue

                smembers.append(i)
                print('Passed member to smembers.')

            return smembers
        
        smembers = SortMembers(members)

        for m in smembers:
            if m.nick:
                name = m.nick
            else:
                name = m.name
            response =  (
                self.supabase.rpc("register", params = {"uid":m.id, "u" : name, "r":"Unknown", "inv_id":None})
                .execute()
            )

        await interaction.response.send_message('Finished migrating.')

        

async def setup(bot):
    await bot.add_cog(Migrate(bot))
