import asyncio
import logging
import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from application_utils import execute_supabase
from deadlock.client import API_ERRORS, resolve_vanity
from deadlock.embeds import display_name
from deadlock.ids import parse_steam_reference

GUILD_ID = int(os.getenv("GUILDID"))
logger = logging.getLogger(__name__)


class ConfirmSteamLink(discord.ui.View):
    def __init__(self, supabase, discord_id: int, steam_id: int):
        super().__init__(timeout=120)
        self.supabase = supabase
        self.discord_id = discord_id
        self.steam_id = steam_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.discord_id:
            return True
        await interaction.response.send_message("Only the person linking Steam can confirm.", ephemeral=True)
        return False

    @discord.ui.button(label="Link this Steam account", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_finished():
            await interaction.response.send_message("This Steam link request is closed.", ephemeral=True)
            return
        self.stop()
        await interaction.response.defer()
        try:
            linked = await execute_supabase(
                self.supabase.table("stats").update({"steam_id": self.steam_id}).eq("discordid", self.discord_id)
            )
        except Exception as error:
            error_code = str(getattr(error, "code", ""))
            if error_code == "23505":
                message = "That Steam account is already linked to another CAA record."
            else:
                logger.exception("Could not save a CAA Steam link")
                if error_code == "42501":
                    message = "Steam linking needs the bot's server-side Supabase key. Ask a CAA admin to check the bot configuration."
                else:
                    message = "The bot couldn't save your Steam link. Try again shortly."
        else:
            message = (
                "Steam linked. Your `/stats` card now has a **View Deadlock Stats** button."
                if linked.data else
                "You need a CAA stats record before you can link Steam."
            )
        await interaction.edit_original_response(content=message, embed=None, view=None)


class SteamLink(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = bot.deadlock
        self.supabase = getattr(bot, "service_supabase", bot.supabase)

    @app_commands.command(name="steam-link", description="Link a Steam Friend Code or profile to your CAA stats.")
    @app_commands.describe(steam="Your numeric Steam Friend Code or Steam Community profile link")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def steam_link(self, interaction: discord.Interaction, steam: str):
        try:
            reference = parse_steam_reference(steam)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            steam_id = await resolve_vanity(reference) if isinstance(reference, str) else reference
        except ValueError as error:
            await interaction.edit_original_response(content=str(error))
            return
        except (aiohttp.ClientError, asyncio.TimeoutError):
            await interaction.edit_original_response(
                content="Steam couldn't load that profile link. Try your numeric Friend Code."
            )
            return

        try:
            profile = await self.client.lookup_steam_profile(steam_id, refresh_missing=True)
        except API_ERRORS:
            await interaction.edit_original_response(
                content="The Steam profile lookup is temporarily unavailable. Try again shortly."
            )
            return
        if not profile:
            await interaction.edit_original_response(
                content="No Steam profile found. Check your Friend Code or profile link and try again."
            )
            return

        embed = discord.Embed(
            title=f"Link {display_name(profile)}?",
            url=profile["profileurl"],
            description=f"Steam ID `#{profile['account_id']}` · Self-reported link",
            color=discord.Color.blurple(),
        )
        if profile.get("avatarfull"):
            embed.set_thumbnail(url=profile["avatarfull"])
        await interaction.edit_original_response(
            embed=embed,
            view=ConfirmSteamLink(self.supabase, interaction.user.id, steam_id),
        )


async def setup(bot):
    await bot.add_cog(SteamLink(bot))
