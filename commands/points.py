from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

GUILD_ID = int(os.getenv("GUILDID"))


class Points(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="points",
        description="Add points to a user."
    )
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    async def points(self, interaction: Interaction, user: discord.User, amount: int):
        if not interaction.user.guild_permissions.manage_events and interaction.user.id != 270202464861421568:
            await interaction.response.send_message("Not available for use.", ephemeral=True)
            return
        self.supabase.rpc("addpoints", params={"uid": user.id, "amnt": amount}).execute()
        await interaction.response.send_message(
            f'Added {amount} points to {user.mention}.', ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Points(bot))
