import os

import discord
from discord import app_commands
from discord.ext import commands

from deadlock.views import show_match

GUILD_ID = int(os.getenv("GUILDID"))


class Match(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = bot.deadlock
        self.supabase = bot.supabase

    @app_commands.command(name="match", description="Look up a Deadlock match and its scoreboard.")
    @app_commands.describe(match_id="The Deadlock match ID")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def match(self, interaction: discord.Interaction, match_id: int):
        if match_id <= 0:
            await interaction.response.send_message("Enter a positive Deadlock match ID.", ephemeral=True)
            return
        await show_match(interaction, self.client, self.supabase, match_id)


async def setup(bot):
    await bot.add_cog(Match(bot))
