from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

from application_utils import fetch_application_record, format_application_date
from config import SERVER_ICON

GUILD_ID = int(os.getenv("GUILDID"))



class Application(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="application",
        description="Retrieve front door application for a specific user."
    ) 
    @app_commands.default_permissions(manage_events=True) 
    @app_commands.guilds(Object(id=GUILD_ID))  
    async def application(self, interaction: Interaction, user: discord.User):

        self.user = user
        data = fetch_application_record(self.supabase, self.user.id)
        if not data:
            await interaction.response.send_message(
                f"No application found for {user.mention}.",
                ephemeral=True
            )
            return

        username = data.get("roblox_username")
        reason = data.get("reason")
        inviter = data.get("inviter")
        inviter_id = data.get("inviter_id")

        embed = discord.Embed(
            title="📄 Entry Request",
            description=f"Submission by {user.mention}",
            color=discord.Color.dark_gray()
        )

        embed.add_field(name="Roblox Username", value=username, inline=True)
        embed.add_field(name="Stated Intent", value=reason, inline=False)
        inviter_text = inviter if inviter else None
        if inviter_id and inviter_text:
            inviter_display = f"{inviter_text} (<@{inviter_id}>)"
        elif inviter_id:
            inviter_display = f"(<@{inviter_id}>)"
        elif inviter_text:
            inviter_display = inviter_text
        else:
            inviter_display = "N/A"

        embed.add_field(name="Referrer", value=inviter_display, inline=False)
        embed.add_field(
            name="Submission Date",
            value=format_application_date(data.get("created_at")),
            inline=False
        )
        embed.set_footer(text = 'Custom Adversaries Association', icon_url=SERVER_ICON)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Application(bot))
