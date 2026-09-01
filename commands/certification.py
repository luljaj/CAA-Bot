from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
import logging
import os
import re
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import Interaction, Object, app_commands
from discord.ext import commands

from application_utils import execute_supabase
from config import (
    CERTIFICATION_COMMAND_CHANNEL_NAMES,
    CERTIFICATION_REVIEW_CHANNEL_ID,
    SERVER_ICON,
    get_certification_role,
    get_employee_role,
)
from review_utils import get_embed_field, replace_embed_field, safe_embed_value


GUILD_ID = int(os.getenv("GUILDID"))
APP_TIMEZONE = ZoneInfo("America/New_York")
CERTIFICATION_REQUEST_TITLE = "🎖️ Teamer Report Certification Request"

logger = logging.getLogger(__name__)


def parse_voucher_entries(value: str) -> list[str]:
    """Parse voucher names entered one per line or separated by commas."""
    return [
        entry.strip()
        for entry in re.split(r"[\n,]+", value)
        if entry.strip()
    ]


def has_two_distinct_vouchers(value: str) -> bool:
    entries = parse_voucher_entries(value)
    return len({entry.casefold() for entry in entries}) >= 2


def is_employee_or_higher(
    member: discord.Member,
    employee_role: discord.Role | None,
) -> bool:
    if employee_role is None:
        return False
    return member.top_role.position >= employee_role.position


def _first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def _display_stat(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    return safe_embed_value(value)


def _truncate(value: str, limit: int = 1024) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"


def _format_awards(value: Any) -> str:
    if not value:
        return "N/A"
    if not isinstance(value, list):
        return _truncate(safe_embed_value(value))

    counts = Counter(str(award) for award in value if str(award).strip())
    if not counts:
        return "N/A"

    lines = [
        f"{award} ({count}x)" if count > 1 else award
        for award, count in counts.items()
    ]
    return _truncate("\n".join(lines))


async def fetch_stats_snapshot(
    supabase: Any,
    member: discord.Member,
) -> dict[str, str]:
    """Fetch the same stats shown by /stats without blocking Discord's event loop."""
    stats: dict[str, Any] = {}
    try:
        response = await execute_supabase(
            supabase.rpc("fetchstats", params={"uid": member.id})
        )
        stats = _first_dict(response.data)
    except Exception:
        logger.warning("Unable to fetch stats for certification applicant %s", member.id)

    invite_count: Any = None
    try:
        response = await execute_supabase(
            supabase.rpc("get_user_invite_count", params={"uid": member.id})
        )
        invite_data = _first_dict(response.data)
        invite_count = invite_data.get("invite_count")
    except Exception:
        logger.warning("Unable to fetch referral count for certification applicant %s", member.id)

    return {
        "Roblox Alias": _display_stat(stats.get("username")),
        "Position": _display_stat(member.top_role.name),
        "Event Wins": _display_stat(stats.get("eventswon")),
        "Referrals": _display_stat(invite_count),
        "Income": _display_stat(stats.get("donations")),
        "Points": _display_stat(stats.get("points")),
        "Reports": _display_stat(stats.get("reports_answered")),
        "Awards": _format_awards(stats.get("awards")),
    }


async def fetch_text_channel(
    bot: commands.Bot,
    channel_id: int,
) -> discord.TextChannel | None:
    channel = bot.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel

    try:
        fetched = await bot.fetch_channel(channel_id)
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        return None
    return fetched if isinstance(fetched, discord.TextChannel) else None


def _application_belongs_to_user(embed: discord.Embed, user_id: int) -> bool:
    value = get_embed_field(embed, "Discord ID")
    if not value:
        return False
    try:
        return int(value.strip()) == user_id
    except (TypeError, ValueError):
        return False


async def has_active_or_approved_application(
    channel: discord.TextChannel,
    user_id: int,
) -> bool:
    async for message in channel.history(limit=None):
        if not message.embeds:
            continue

        embed = message.embeds[0]
        if embed.title != CERTIFICATION_REQUEST_TITLE:
            continue
        if not _application_belongs_to_user(embed, user_id):
            continue

        status = get_embed_field(embed, "Status") or ""
        if status == "In Review" or status.startswith("Approved by "):
            return True
    return False


def _channel_is_allowed(channel: discord.abc.GuildChannel | None) -> bool:
    channel_name = getattr(channel, "name", "")
    return channel_name.lower() in CERTIFICATION_COMMAND_CHANNEL_NAMES


class CertificationModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot, cog: "Certification"):
        super().__init__(title="Teamer Report Certification", timeout=None)
        self.bot = bot
        self.supabase = bot.supabase
        self.cog = cog

        self.vouchers = discord.ui.TextInput(
            label="Who can vouch for your standing?",
            style=discord.TextStyle.paragraph,
            placeholder="List at least two distinct Discord members, preferably one per line.",
            max_length=1024,
            required=True,
        )
        self.reason = discord.ui.TextInput(
            label="Why do you want certification?",
            style=discord.TextStyle.paragraph,
            placeholder="Explain why you should receive the Teamer Report Certification role.",
            max_length=1024,
            required=True,
        )

        self.add_item(self.vouchers)
        self.add_item(self.reason)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.edit_original_response(
                content="This command can only be used in the server."
            )
            return

        if not has_two_distinct_vouchers(self.vouchers.value):
            await interaction.edit_original_response(
                content="Please list at least two distinct voucher names."
            )
            return

        reason = self.reason.value.strip()
        if not reason:
            await interaction.edit_original_response(
                content="Please explain why you want the certification role."
            )
            return

        async with self.cog._submission_lock:
            employee_role = get_employee_role(interaction.guild)
            if employee_role is None:
                await interaction.edit_original_response(
                    content="The Employee role is not configured. Please contact staff."
                )
                return
            if not is_employee_or_higher(interaction.user, employee_role):
                await interaction.edit_original_response(
                    content="Only Employees and higher-ranked members can apply for certification."
                )
                return

            certification_role = get_certification_role(interaction.guild)
            if certification_role is None:
                await interaction.edit_original_response(
                    content="The Teamer Report Certification role is not configured. Please contact staff."
                )
                return
            if certification_role in interaction.user.roles:
                await interaction.edit_original_response(
                    content="You already have the Teamer Report Certification role."
                )
                return

            if not _channel_is_allowed(interaction.channel):
                await interaction.edit_original_response(
                    content="Certification applications can only be submitted in #bot-commands or #hbg-certification."
                )
                return

            review_channel = await fetch_text_channel(
                self.bot,
                CERTIFICATION_REVIEW_CHANNEL_ID,
            )
            if review_channel is None:
                await interaction.edit_original_response(
                    content="The certification review channel is unavailable. Please contact staff."
                )
                return

            if await has_active_or_approved_application(review_channel, interaction.user.id):
                await interaction.edit_original_response(
                    content="You already have a certification application in review or an approved application."
                )
                return

            stats = await fetch_stats_snapshot(self.supabase, interaction.user)
            submitted_at = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d %H:%M %Z")

            embed = discord.Embed(
                title=CERTIFICATION_REQUEST_TITLE,
                description=f"Submission at {submitted_at}",
                color=discord.Color.gold(),
            )
            embed.add_field(name="Applicant", value=interaction.user.mention, inline=False)
            embed.add_field(name="Discord ID", value=str(interaction.user.id), inline=False)
            embed.add_field(
                name="Voucher Names",
                value=_truncate(safe_embed_value(self.vouchers.value)),
                inline=False,
            )
            embed.add_field(
                name="Reason",
                value=_truncate(safe_embed_value(reason)),
                inline=False,
            )
            embed.add_field(
                name="Stats Snapshot",
                value="Captured at submission time.",
                inline=False,
            )
            for name, value in stats.items():
                embed.add_field(name=name, value=value, inline=True)
            embed.add_field(name="Status", value="In Review", inline=False)
            embed.set_footer(text="Custom Adversaries Association", icon_url=SERVER_ICON)

        try:
            message = await review_channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            await message.add_reaction("✅")
            await message.add_reaction("❌")
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Unable to send certification review for %s", interaction.user.id)
            await interaction.edit_original_response(
                content="The certification application could not be sent for review. Please contact staff."
            )
            return

        await interaction.edit_original_response(
            content="Your certification application has been sent for staff review."
        )


class Certification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._submission_lock = asyncio.Lock()
        self._processing_messages: set[int] = set()

    async def _fetch_review_message(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> tuple[
        discord.Guild | None,
        discord.Member | None,
        discord.Message | None,
    ]:
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return None, None, None

        member = payload.member or guild.get_member(payload.user_id)
        channel = guild.get_channel(payload.channel_id)
        if channel is None:
            try:
                fetched = await self.bot.fetch_channel(payload.channel_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                return guild, member, None
            channel = fetched if isinstance(fetched, discord.TextChannel) else None
        if channel is None:
            return guild, member, None

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return guild, member, None
        return guild, member, message

    @app_commands.command(
        name="certification",
        description="Apply for the Teamer Report Certification role.",
    )
    @app_commands.guilds(Object(id=GUILD_ID))
    async def certification(self, interaction: Interaction):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used in the server.",
                ephemeral=True,
            )
            return

        if not _channel_is_allowed(interaction.channel):
            await interaction.response.send_message(
                "Certification applications can only be submitted in #bot-commands or #hbg-certification.",
                ephemeral=True,
            )
            return

        employee_role = get_employee_role(interaction.guild)
        if employee_role is None:
            await interaction.response.send_message(
                "The Employee role is not configured. Please contact staff.",
                ephemeral=True,
            )
            return
        if not is_employee_or_higher(interaction.user, employee_role):
            await interaction.response.send_message(
                "Only Employees and higher-ranked members can apply for certification.",
                ephemeral=True,
            )
            return

        certification_role = get_certification_role(interaction.guild)
        if certification_role is None:
            await interaction.response.send_message(
                "The Teamer Report Certification role is not configured. Please contact staff.",
                ephemeral=True,
            )
            return
        if certification_role in interaction.user.roles:
            await interaction.response.send_message(
                "You already have the Teamer Report Certification role.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(CertificationModal(self.bot, self))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if (
            self.bot.user is not None
            and payload.user_id == self.bot.user.id
        ) or str(payload.emoji) not in ("✅", "❌"):
            return

        if payload.message_id in self._processing_messages:
            return
        self._processing_messages.add(payload.message_id)

        try:
            await self._handle_review_reaction(payload)
        finally:
            self._processing_messages.discard(payload.message_id)

    async def _handle_review_reaction(
        self,
        payload: discord.RawReactionActionEvent,
    ):
        guild, member, message = await self._fetch_review_message(payload)
        if guild is None or member is None or message is None or not message.embeds:
            return
        if not member.guild_permissions.manage_roles:
            return

        embed = message.embeds[0]
        if embed.title != CERTIFICATION_REQUEST_TITLE:
            return
        if get_embed_field(embed, "Status") != "In Review":
            return

        applicant_id_value = get_embed_field(embed, "Discord ID")
        try:
            applicant_id = int(applicant_id_value or "")
        except (TypeError, ValueError):
            return

        applicant = guild.get_member(applicant_id)
        if applicant is None:
            try:
                applicant = await guild.fetch_member(applicant_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                return

        approved = str(payload.emoji) == "✅"
        certification_role = get_certification_role(guild)
        if approved:
            if certification_role is None or not self._role_is_assignable(
                guild,
                certification_role,
            ):
                logger.error("Certification role is missing or unmanageable")
                return

            if certification_role not in applicant.roles:
                try:
                    await applicant.add_roles(
                        certification_role,
                        reason=f"Certification request approved by {member}",
                    )
                except (discord.Forbidden, discord.HTTPException):
                    logger.exception(
                        "Unable to assign certification role to %s",
                        applicant.id,
                    )
                    return

        new_embed = embed.copy()
        new_embed.color = discord.Color.green() if approved else discord.Color.red()
        replace_embed_field(
            new_embed,
            "Status",
            f"{'Approved' if approved else 'Denied'} by {member.display_name}",
            inline=False,
        )

        try:
            await message.edit(embed=new_embed)
            await message.clear_reactions()
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Unable to finalize certification review %s", message.id)

        try:
            await applicant.send(
                "Your certification request was approved. You have been given the Teamer Report Certification role."
                if approved
                else "Your certification request was denied by staff."
            )
        except discord.HTTPException:
            pass

    @staticmethod
    def _role_is_assignable(
        guild: discord.Guild,
        role: discord.Role,
    ) -> bool:
        if role.managed:
            return False
        bot_member = guild.me
        if bot_member is None:
            return False
        return role < bot_member.top_role


async def setup(bot: commands.Bot):
    await bot.add_cog(Certification(bot))
