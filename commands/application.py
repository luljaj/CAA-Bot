from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import supabase

GUILD_ID = int(os.getenv("GUILDID"))



class Application(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="application",
        description="Retrieve front door application for a specific user."
    )
    @app_commands.checks.has_permissions(manage_events=True)  
    @app_commands.guilds(Object(id=GUILD_ID))  
    async def application(self, interaction: Interaction, user: discord.User):

        self.user = user
        
        response = (
                self.supabase.rpc("fetchapplication", params = {"uid": self.user.id})
                .execute()
            )

        if not response:
            await interaction.response.send_message(
                f"No application found for {user.mention}.",
                ephemeral=True
            )
            return

        id, discordid, username, reason, inviter, date = response.data.values()

        embed = discord.Embed(
            title="📄 Entry Request",
            description=f"Submission by {user.mention}",
            color=discord.Color.dark_gray()
        )
        embed.add_field(name="Roblox Username", value=username, inline=True)
        embed.add_field(name="Stated Intent", value=reason, inline=False)
        embed.add_field(name="Referrer", value=inviter or "N/A", inline=False)
        embed.add_field(name="Submission Date", value=date or "N/A", inline=False)
        embed.set_footer(text = 'Custom Adversaries Association', icon_url='https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024')

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Application(bot))
