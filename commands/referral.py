from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

GUILD_ID = int(os.getenv("GUILDID"))


class Referral(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="referral",
        description="Set your referrer (one-time)."
    )
    @app_commands.guilds(Object(id=GUILD_ID))
    async def referral(self, interaction: Interaction, user: discord.User):
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot set yourself as your referrer.",
                ephemeral=True
            )
            return

        if user.bot:
            await interaction.response.send_message(
                "Bots cannot be set as referrers.",
                ephemeral=True
            )
            return

        app_response = (
            self.supabase.rpc("fetchapplication", params={"uid": interaction.user.id})
            .execute()
        )
        if not app_response.data:
            await interaction.response.send_message(
                "No application found for you. Please register first.",
                ephemeral=True
            )
            return

        app_data = (
            app_response.data[0]
            if isinstance(app_response.data, list)
            else app_response.data
        )
        inviter_id = None
        if isinstance(app_data, dict):
            inviter_id = app_data.get("inviter_id")
        elif hasattr(app_data, "values"):
            values = list(app_data.values())
            inviter_id = values[6] if len(values) > 6 else None

        if inviter_id:
            await interaction.response.send_message(
                "You already have a referrer. Contact staff to change it.",
                ephemeral=True
            )
            return

        update_response = (
            self.supabase.rpc(
                "update_referral",
                params={"uid": interaction.user.id, "ref_id": user.id}
            )
            .execute()
        )
        update_data = (
            update_response.data[0]
            if isinstance(update_response.data, list)
            else update_response.data
        )

        success = True
        message = None
        if isinstance(update_data, dict):
            success = update_data.get("success", True)
            message = update_data.get("message")

        if not success:
            await interaction.response.send_message(
                message or "Failed to set your referrer.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Set referrer to {user.mention}.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Referral(bot))
