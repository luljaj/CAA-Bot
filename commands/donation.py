from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

GUILD_ID = int(os.getenv("GUILDID"))


def larnagack():
    async def predicate(interaction: Interaction) -> bool:
        if interaction.user.id != 270202464861421568:
            raise app_commands.CheckFailure("Not available for use.")
        return True
    return app_commands.check(predicate)


class Donation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="donation",
        description="Log a donation for a user."
    )
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    async def donation(self, interaction: Interaction, user: discord.User, amount: int):
        if not interaction.user.guild_permissions.manage_events and interaction.user.id != 270202464861421568:
            await interaction.response.send_message("Not available for use.", ephemeral=True)
            return
        self.supabase.rpc("adddonations", params={"uid": user.id, "amnt": amount}).execute()
        await interaction.response.send_message(
            f'Logged donation of {amount} for {user.mention}.', ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Donation(bot))
