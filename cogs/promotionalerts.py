from datetime import datetime, timedelta, timezone
import os

import discord
from discord.ext import commands, tasks

from application_utils import fetch_application_record, format_application_date
from config import (
    ENTRY_REVIEW_CHANNEL_ID,
    PROMOTION_REVIEW_CHANNEL_ID,
    SERVER_ICON,
    get_intern_role,
    get_promotion_rollout_cutoff,
)
from review_utils import (
    REGISTER_REQUEST_MARKER,
    get_embed_field,
    parse_footer_marker,
    safe_embed_value,
)


GUILD_ID = int(os.getenv("GUILDID"))


class PromotionAlerts(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rollout_cutoff = get_promotion_rollout_cutoff().astimezone(timezone.utc)
        self.intern_alerts.start()

    def cog_unload(self):
        self.intern_alerts.cancel()

    async def _get_text_channel(self, channel_id: int) -> discord.TextChannel | None:
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel

        fetched = await self.bot.fetch_channel(channel_id)
        return fetched if isinstance(fetched, discord.TextChannel) else None

    async def _collect_existing_alert_markers(
        self, channel: discord.TextChannel
    ) -> set[tuple[int, int]]:
        markers: set[tuple[int, int]] = set()
        async for message in channel.history(limit=500):
            if not message.embeds:
                continue

            embed = message.embeds[0]
            if embed.title != "⏰ Intern Promotion Follow-Up":
                continue

            user_id = get_embed_field(embed, "Discord ID")
            week_marker = get_embed_field(embed, "Alert Week")
            if user_id and week_marker:
                markers.add((int(user_id), int(week_marker)))

        return markers

    async def _collect_rollout_eligible_intern_ids(
        self, channel: discord.TextChannel
    ) -> set[int]:
        eligible_intern_ids: set[int] = set()
        async for message in channel.history(limit=None):
            if not message.embeds:
                continue

            embed = message.embeds[0]
            marker_type, marker_values = parse_footer_marker(embed.footer.text)
            if marker_type != REGISTER_REQUEST_MARKER:
                continue

            status = get_embed_field(embed, "Status") or ""
            if not status.startswith("Approved by "):
                continue

            resolved_at = (message.edited_at or message.created_at).astimezone(timezone.utc)
            if resolved_at < self.rollout_cutoff:
                continue

            user_id = marker_values.get("user_id") or get_embed_field(embed, "Discord ID")
            if user_id:
                eligible_intern_ids.add(int(user_id))

        return eligible_intern_ids

    async def _send_alert(
        self,
        channel: discord.TextChannel,
        member: discord.Member,
        application_record: dict[str, object],
        week_marker: int,
    ):
        roblox_name = (
            application_record.get("roblox_username")
            or member.nick
            or member.display_name
        )

        embed = discord.Embed(
            title="⏰ Intern Promotion Follow-Up",
            description=(
                f"{member.mention} is still an Intern {week_marker} weeks after their application date."
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(name="Applicant", value=member.mention, inline=False)
        embed.add_field(name="Discord ID", value=str(member.id), inline=False)
        embed.add_field(
            name="Roblox Name / Nickname",
            value=safe_embed_value(roblox_name),
            inline=False,
        )
        embed.add_field(
            name="Application Date",
            value=format_application_date(application_record.get("created_at")),
            inline=False,
        )
        embed.add_field(name="Alert Week", value=str(week_marker), inline=False)
        embed.set_footer(
            text="Custom Adversaries Association",
            icon_url=SERVER_ICON,
        )

        await channel.send(
            content=f"Promotion follow-up for {member.mention}.",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=False,
            ),
        )

    @tasks.loop(hours=24.0)
    async def intern_alerts(self):
        if not self.bot.is_ready():
            return

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            return

        promotion_review_channel = await self._get_text_channel(PROMOTION_REVIEW_CHANNEL_ID)
        entry_review_channel = await self._get_text_channel(ENTRY_REVIEW_CHANNEL_ID)
        intern_role = get_intern_role(guild)
        if (
            promotion_review_channel is None
            or entry_review_channel is None
            or intern_role is None
        ):
            return

        existing_alerts = await self._collect_existing_alert_markers(
            promotion_review_channel
        )
        rollout_eligible_ids = await self._collect_rollout_eligible_intern_ids(
            entry_review_channel
        )

        now = datetime.now(timezone.utc)
        for member in intern_role.members:
            if member.bot or member.id not in rollout_eligible_ids:
                continue

            application_record = fetch_application_record(self.bot.supabase, member.id)
            if not application_record:
                continue

            application_date = application_record.get("created_at")
            if application_date is None:
                continue

            elapsed = now - application_date.astimezone(timezone.utc)
            if elapsed < timedelta(weeks=6):
                continue

            week_marker = elapsed.days // 7
            marker = (member.id, week_marker)
            if marker in existing_alerts:
                continue

            await self._send_alert(
                promotion_review_channel,
                member,
                application_record,
                week_marker,
            )
            existing_alerts.add(marker)

    @intern_alerts.before_loop
    async def before_intern_alerts(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(PromotionAlerts(bot))
