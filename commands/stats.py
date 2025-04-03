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
REVIEW_CHANNEL = 1356017239039414615


def getUserId(user):
    user = 'larnagack'
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

    @app_commands.command(
        name="stats",
        description="Retrieve a users stats."
    )
    @app_commands.guilds(Object(id=GUILD_ID)) 
    async def stats(self, interaction: Interaction, user: discord.User):
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, cash, reports, eventswon FROM stats WHERE discordid = ?",
                (user.id,)
            )
            row = cursor.fetchone()
            cursor.execute("SELECT awards FROM stats WHERE discordid = ?", (user.id,))
            awards = json.loads(cursor.fetchone()[0])
            print(awards)

        if not row:
            await interaction.response.send_message(
                f"No stats found for {user.mention}.",
                ephemeral=True
            )
            return

        username, cash, reports, eventswon = row
        avatar_url = user.avatar.url
        user_id = getUserId(username)
        avatar_thumbnail = requests.get(f'https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png')
        if avatar_thumbnail:
            avatar_url = avatar_thumbnail.json()["data"][0]["imageUrl"]
        rank = user.top_role

        embed = discord.Embed(
            title=f"📂 {user.name} - EMPLOYEE RECORD",
            color=rank.color
        )

        
        inline = True
        embed.add_field(name="ROLODEX ENTRY", value="", inline=False)
        embed.add_field(name="ALIAS", value=username, inline=inline)
        embed.add_field(name="POSITION", value=f'{rank.name}', inline=inline)
        embed.add_field(name="BALANCE", value=f'${cash}', inline=inline)
        embed.add_field(name="PERFORMANCE FILE", value="", inline=False)
        embed.add_field(name="REPORTS", value=reports, inline=inline)
        embed.add_field(name="EVENT WINS", value=eventswon, inline=inline)
        embed.add_field(name = f'AWARDS ({len(awards)})', value = "\n".join(awards), inline = False)
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text = 'Custom Adversaries Association', icon_url='https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024')

        await interaction.response.send_message(embed=embed)








async def setup(bot):
    await bot.add_cog(Stats(bot))
