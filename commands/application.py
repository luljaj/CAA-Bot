from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord

# Environment and config
db_folder = './databases'
db_file = os.path.join(db_folder, 'applications.db')
GUILD_ID = int(os.getenv("GUILDID"))
REVIEW_CHANNEL = 1356017239039414615


class Application(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="application",
        description="Retrieve front door application for a specific user."
    )
    @app_commands.checks.has_permissions(manage_events=True)  # ✅ Permission required
    @app_commands.guilds(Object(id=GUILD_ID))  # ✅ Guild-specific registration
    async def application(self, interaction: Interaction, user: discord.User):
        # Pull the application from the database
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, reason, inviter FROM applications WHERE discordid = ?",
                (user.id,)
            )
            row = cursor.fetchone()

        if not row:
            await interaction.response.send_message(
                f"No application found for {user.mention}.",
                ephemeral=True
            )
            return

        username, reason, inviter = row

        embed = discord.Embed(
            title="📄 Application Details",
            description=f"Application submitted by {user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Roblox Username", value=username, inline=True)
        embed.add_field(name="Reason for Entry", value=reason, inline=False)
        embed.add_field(name="Referrer", value=inviter or "N/A", inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Application(bot))
