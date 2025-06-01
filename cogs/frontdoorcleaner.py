from discord.ext import commands, tasks
from discord import Interaction
import os
import discord

CHANNEL_ID = 1355935366867062826
ALLOWED_USERS = [1355933950018584876]

class FrontDoorCleaner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.fdc.start()
        self.channel_id = CHANNEL_ID

    def cog_unload(self):
        self.fdc.cancel()

    @tasks.loop(minutes=1.0)
    async def fdc(self):
        channel = self.bot.get_channel(self.channel_id)
        if not self.bot.is_ready():
            return

        def should_delete(message):
            return message.author.id not in ALLOWED_USERS

        try:
            await channel.purge(limit=100, check=should_delete)
        except Exception:
            pass

    @fdc.before_loop
    async def before_fdc(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(FrontDoorCleaner(bot))
