from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
import supabase
from datetime import datetime


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
        
        response = (
                self.supabase.rpc("fetchapplication", params = {"uid": self.user.id})
                .execute()
            )

        if not response.data:
            await interaction.response.send_message(
                f"No application found for {user.mention}.",
                ephemeral=True
            )
            return

        data = response.data
        if isinstance(data, list):
            if not data:
                await interaction.response.send_message(
                    f"No application found for {user.mention}.",
                    ephemeral=True
                )
                return
            data = data[0]

        if isinstance(data, dict):
            username = data.get("roblox_username") or data.get("username")
            reason = data.get("reason")
            inviter = data.get("inviter")
            inviter_id = data.get("inviter_id")
            raw_date = (
                data.get("created_at")
                or data.get("submission_date")
                or data.get("created")
                or data.get("raw_date")
            )
        else:
            values = list(data.values()) if hasattr(data, "values") else []
            username = values[2] if len(values) > 2 else None
            reason = values[3] if len(values) > 3 else None
            inviter = values[4] if len(values) > 4 else None
            raw_date = values[5] if len(values) > 5 else None
            inviter_id = values[6] if len(values) > 6 else None

        embed = discord.Embed(
            title="📄 Entry Request",
            description=f"Submission by {user.mention}",
            color=discord.Color.dark_gray()
        )

        formatted = "N/A"
        if raw_date:
            if isinstance(raw_date, str) and '.' in raw_date:
                date_part, micro = raw_date.split('.')
                micro = (micro + '000000')[:6]
                raw_date = f"{date_part}.{micro}"
            dt = datetime.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
            formatted = dt.strftime("%Y-%m-%d %H:%M") 

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
        embed.add_field(name="Submission Date", value=formatted or "N/A", inline=False)
        embed.set_footer(text = 'Custom Adversaries Association', icon_url='https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024')

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Application(bot))
