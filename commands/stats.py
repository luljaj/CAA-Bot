from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import logging
import discord
from collections import defaultdict
import aiohttp

from application_utils import execute_supabase
from config import SERVER_ICON
from deadlock.views import EmployeeRecord, EmployeeRecordView
from position_utils import position_role

GUILD_ID = int(os.getenv("GUILDID"))
logger = logging.getLogger(__name__)


async def getUserId(user):
    url = f'https://www.roblox.com/users/profile?username={user}'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True) as resp:
                final_url = str(resp.url)
    except Exception:
        return None

    lurl = final_url.split('/')
    if len(lurl) > 4:
        return lurl[4]
    return None

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

        await interaction.response.defer(thinking=True)


        response = (
                    self.supabase.rpc("fetchstats", params = {"uid": user.id})
                    .execute())

        if not response.data:
            await interaction.followup.send(
                f"No stats found for {user.mention}.",
                ephemeral=True
            )
            return
        

        data = response.data
        id = data["id"]
        discordid = data["discordid"]
        username = data["username"]
        eventswon = data["eventswon"]
        awards = data["awards"]
        reports_answered = data.get("reports_answered", 0) or 0

        invite_count = 0
        invite_response = (
            self.supabase.rpc("get_user_invite_count", params={"uid": user.id})
            .execute()
        )
        if invite_response.data:
            invite_data = invite_response.data[0] if isinstance(invite_response.data, list) else invite_response.data
            if isinstance(invite_data, dict):
                invite_count = invite_data.get("invite_count", 0) or 0

        avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
        try:
            user_id = await getUserId(username)
            if user_id:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png'
                    ) as avatar_thumbnail:
                        avatar_data = await avatar_thumbnail.json()
                        avatar_url = avatar_data["data"][0]["imageUrl"]
        except Exception:
            pass
        
        rank = position_role(user)

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
        embed.add_field(name="REFERRALS", value=invite_count, inline=inline)
        embed.add_field(name="REPORTS", value=reports_answered, inline=inline)
        embed.add_field(name = f'AWARDS ({len(awards)})', value = awardsdisplay, inline = False)
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text = 'Custom Adversaries Association', icon_url=SERVER_ICON)

        deadlock = getattr(self.bot, "deadlock", None)
        if deadlock is not None:
            steam_id = data.get("steam_id")
            if "steam_id" not in data:
                try:
                    linked = await execute_supabase(
                        self.supabase.table("stats").select("steam_id").eq("discordid", user.id).limit(1)
                    )
                    if linked.data:
                        steam_id = linked.data[0]["steam_id"]
                except Exception:
                    logger.exception("Could not read the Steam link for a CAA record")
            if steam_id:
                view = EmployeeRecordView(deadlock, self.supabase, EmployeeRecord(embed, int(steam_id)))
                await interaction.followup.send(embed=embed, view=view)
                return

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))
