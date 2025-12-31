from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

GUILD_ID = int(os.getenv("GUILDID"))


class Updatereferral(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="updatereferral",
        description="Update a user's referrer."
    )
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    async def updatereferral(
        self,
        interaction: Interaction,
        user: discord.User,
        new_referrer: discord.User
    ):
        if user.id == new_referrer.id:
            await interaction.response.send_message(
                "A user cannot be their own referrer.",
                ephemeral=True
            )
            return

        if new_referrer.bot:
            await interaction.response.send_message(
                "Bots cannot be set as referrers.",
                ephemeral=True
            )
            return

        update_response = (
            self.supabase.rpc(
                "update_referral",
                params={"uid": user.id, "ref_id": new_referrer.id}
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
        old_inviter = None
        old_inviter_id = None
        if isinstance(update_data, dict):
            success = update_data.get("success", True)
            message = update_data.get("message")
            old_inviter = update_data.get("old_inviter")
            old_inviter_id = update_data.get("old_inviter_id")

        if not success:
            await interaction.response.send_message(
                message or "Failed to update referrer.",
                ephemeral=True
            )
            return

        if old_inviter and old_inviter_id:
            previous_display = f"{old_inviter} (<@{old_inviter_id}>)"
        elif old_inviter_id:
            previous_display = f"<@{old_inviter_id}>"
        elif old_inviter:
            previous_display = old_inviter
        else:
            previous_display = "N/A"

        await interaction.response.send_message(
            (
                f"Updated {user.mention}'s referrer to {new_referrer.mention}.\n"
                f"Previous: {previous_display}"
            ),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Updatereferral(bot))
