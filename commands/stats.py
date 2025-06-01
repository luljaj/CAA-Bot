from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import requests
import json
from collections import defaultdict
from dotenv import load_dotenv

GUILD_ID = int(os.getenv("GUILDID"))


def getUserId(user):
    try:
        link = requests.get(f'https://www.roblox.com/users/profile?username={user}')
    except:
        return None
    url =  link.url
    lurl = url.split('/')
    id = lurl[4]
    return id

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="stats",
        description="Retrieve a users stats."
    )
    @app_commands.guilds(Object(id=GUILD_ID)) 
    async def stats(self, interaction: Interaction, user: discord.User):
        response = (
                    self.supabase.rpc("fetchstats", params = {"uid": user.id})
                    .execute())

        if not response:
            await interaction.response.send_message(
                f"No stats found for {user.mention}.",
                ephemeral=True
            )
            return

        id, discordid, username, eventswon, awards = response.data.values()

        avatar_url = user.avatar.url
        user_id = getUserId(username)
        avatar_thumbnail = requests.get(f'https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png')
        if avatar_thumbnail:
            try:
                avatar_url = avatar_thumbnail.json()["data"][0]["imageUrl"]
            except:
                None
        
        rank = user.top_role

        roles = user.roles

        roles.reverse()

        normal = 'Event Winner', 'Server Booster'

        for i in roles:
            if i.name in normal:
                continue
            else:
                rank = i
                break

        embed = discord.Embed(
            title=f"📂 {user.name} - EMPLOYEE RECORD",
            color=rank.color
        )

        awardsdisplay = ""
        awardscount = defaultdict(int)
        for i in awards:
            awardscount[i] += 1
        for i in awardscount.keys():
            if awardscount[i] == 1:
                awardsdisplay += i + '\n'
            else:
                awardsdisplay += i + f' ({awardscount[i]}x) \n'
                
        inline = True
        embed.add_field(name=f"ROLODEX ENTRY #{id}", value="", inline=False)
        embed.add_field(name="ALIAS", value=username, inline=inline)
        embed.add_field(name="POSITION", value=f'{rank.name}', inline=inline)
        embed.add_field(name="PERFORMANCE FILE", value="", inline=False)
        embed.add_field(name="EVENT WINS", value=eventswon, inline=inline)
        embed.add_field(name = f'AWARDS ({len(awards)})', value = awardsdisplay, inline = False)
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text = 'Custom Adversaries Association', icon_url='https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024')

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))
