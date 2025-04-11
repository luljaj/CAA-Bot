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


def getUserId(user):
    try:
        link = requests.get(f'https://www.roblox.com/users/profile?username={user}')
    except:
        return None
    url =  link.url
    lurl = url.split('/')
    id = lurl[4]
    return id

class Ranking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="rankings",
        description="Retrieve the CAA Cash Rankings."
    )

    @app_commands.choices(slot = [app_commands.Choice(name = 'Cash', value = 'cash'),
            app_commands.Choice(name = 'Reports', value = 'reports'),
            app_commands.Choice(name = 'Events Won', value = 'eventswon')])
    
    @app_commands.guilds(Object(id=GUILD_ID)) 
    async def ranking(self, interaction: Interaction, user: discord.User):
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT * FROM stats ORDER BY score DESC LIMIT 3;')
            users = cursor.fetchall()

        if not users:
            await interaction.response.send_message(
                f"No stats found for {user.mention}.",
                ephemeral=True
            )
            return

        avatar_url = user.avatar.url
        user_id = getUserId(username)
        avatar_thumbnail = requests.get(f'https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png')
        if avatar_thumbnail:
            try:
                avatar_url = avatar_thumbnail.json()["data"][0]["imageUrl"]
            except:
                None
            
        rank = user.top_role

        embed = discord.Embed(
            title=f"📂 C.A.A CASH RANKINGS",
            color=rank.color
        )

        
        embed.set_footer(text = 'Custom Adversaries Association', icon_url='https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024')

        await interaction.response.send_message(embed=embed)








async def setup(bot):
    await bot.add_cog(Ranking(bot))
