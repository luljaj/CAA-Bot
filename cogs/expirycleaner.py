from discord.ext import commands, tasks
import os
import discord

from application_utils import execute_supabase

GUILD_ID = int(os.getenv("GUILDID"))
REPORT_BAN_ROLE = "Teamer Banned"


class ExpiryCleaner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.report_bans.start()
        self.purge_strikes.start()

    def cog_unload(self):
        self.report_bans.cancel()
        self.purge_strikes.cancel()

    @tasks.loop(minutes=5.0)
    async def report_bans(self):
        if not self.bot.is_ready():
            return
        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            return
        role = discord.utils.get(guild.roles, name=REPORT_BAN_ROLE)
        if role is None:
            return
        expired_response = await execute_supabase(
            self.bot.supabase.rpc("get_expired_report_bans")
        )
        expired = expired_response.data or []
        for entry in expired:
            member = guild.get_member(entry["user_id"])
            if member and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Report ban expired")
                except Exception:
                    pass
            await execute_supabase(
                self.bot.supabase.rpc(
                    "unban_user_report",
                    {"user_id": entry["user_id"]},
                )
            )

    @report_bans.before_loop
    async def before_report_bans(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24.0)
    async def purge_strikes(self):
        if not self.bot.is_ready():
            return
        await execute_supabase(self.bot.supabase.rpc("purge_expired_strikes"))

    @purge_strikes.before_loop
    async def before_purge_strikes(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ExpiryCleaner(bot))
