from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

GUILD_ID = int(os.getenv("GUILDID"))


class Editreports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(name="editreportcount", description="Change an employee's report count.")
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    async def editreportcount(self, interaction: Interaction, user: discord.User, value: int):
        if not 0 <= value <= 9999:
            await interaction.response.send_message("Value must be between 0 and 9999.", ephemeral=True)
            return
        self.supabase.rpc("set_report_count", params={"edit_val": value, "uid": user.id}).execute()
        await interaction.response.send_message(
            f"{user.mention}'s report count is now {value}.", ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Editreports(bot))
