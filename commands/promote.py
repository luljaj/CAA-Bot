from datetime import datetime, timedelta
import os

import discord
from discord import Interaction, Object, app_commands
from discord.ext import commands
from zoneinfo import ZoneInfo

from application_utils import fetch_application_record, format_application_date
from config import (
    PROMOTION_REVIEW_CHANNEL_ID,
    SERVER_ICON,
    get_employee_role,
    get_intern_role,
)
from review_utils import (
    PROMOTION_REQUEST_MARKER,
    build_footer_text,
    get_embed_field,
    parse_footer_marker,
    replace_embed_field,
    safe_embed_value,
)


GUILD_ID = int(os.getenv("GUILDID"))
APP_TIMEZONE = ZoneInfo("America/New_York")


class PromoteModal(discord.ui.Modal):
    def __init__(self, bot, application_record: dict[str, object]):
        super().__init__(title="Promotion Request", timeout=None)
        self.bot = bot
        self.application_record = application_record

        self.references = discord.ui.TextInput(
            label="Who are two members who can testify to your CAA contributions?",
            style=discord.TextStyle.paragraph,
            placeholder="Both must be Respected or above.",
            max_length=1024,
            required=True,
        )
        self.statement = discord.ui.TextInput(
            label="Why do you want to be an employee in the CAA?",
            style=discord.TextStyle.paragraph,
            placeholder="2 sentence minimum",
            max_length=1024,
            required=True,
        )

        self.add_item(self.references)
        self.add_item(self.statement)

    async def on_submit(self, interaction: Interaction):
        channel = self.bot.get_channel(PROMOTION_REVIEW_CHANNEL_ID)
        if channel is None:
            channel = await self.bot.fetch_channel(PROMOTION_REVIEW_CHANNEL_ID)

        roblox_name = (
            self.application_record.get("roblox_username")
            or interaction.user.nick
            or interaction.user.display_name
        )
        submitted_at = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d %H:%M %Z")

        embed = discord.Embed(
            title="📈 Promotion Request",
            description=f"Submission at {submitted_at}",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Applicant", value=interaction.user.mention, inline=False)
        embed.add_field(name="Discord ID", value=str(interaction.user.id), inline=False)
        embed.add_field(
            name="Roblox Name / Nickname",
            value=safe_embed_value(roblox_name),
            inline=False,
        )
        embed.add_field(
            name="Application Date",
            value=format_application_date(self.application_record.get("created_at")),
            inline=False,
        )
        embed.add_field(name="References", value=self.references.value, inline=False)
        embed.add_field(name="Statement", value=self.statement.value, inline=False)
        embed.add_field(name="Status", value="In Review", inline=False)
        embed.set_footer(
            text=build_footer_text(PROMOTION_REQUEST_MARKER, user_id=interaction.user.id),
            icon_url=SERVER_ICON,
        )

        message = await channel.send(embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        await interaction.response.send_message(
            "Your promotion request has been sent for staff review.",
            ephemeral=True,
        )


class Promote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    async def _fetch_review_message(
        self, payload: discord.RawReactionActionEvent
    ) -> tuple[discord.Guild, discord.Member | None, discord.Message] | tuple[None, None, None]:
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return None, None, None

        member = payload.member or guild.get_member(payload.user_id)
        channel = guild.get_channel(payload.channel_id)
        if channel is None:
            fetched = await self.bot.fetch_channel(payload.channel_id)
            channel = fetched if isinstance(fetched, discord.TextChannel) else None
        if channel is None:
            return None, member, None

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return guild, member, None
        return guild, member, message

    @app_commands.command(
        name="promote",
        description="Request promotion from Intern to Employee."
    )
    @app_commands.guilds(Object(id=GUILD_ID))
    async def promote(self, interaction: Interaction):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used in the server.",
                ephemeral=True,
            )
            return

        intern_role = get_intern_role(interaction.guild)
        if intern_role is None or intern_role not in interaction.user.roles:
            await interaction.response.send_message(
                "Only members with the Intern role can use /promote.",
                ephemeral=True,
            )
            return

        application_record = fetch_application_record(self.supabase, interaction.user.id)
        if not application_record:
            await interaction.response.send_message(
                "No application record was found for you, so /promote is unavailable.",
                ephemeral=True,
            )
            return

        application_date = application_record.get("created_at")
        if application_date is None:
            await interaction.response.send_message(
                "Your application date could not be determined.",
                ephemeral=True,
            )
            return

        eligible_at = application_date + timedelta(days=7)
        now = datetime.now(APP_TIMEZONE)
        if now < eligible_at:
            await interaction.response.send_message(
                (
                    "You are not eligible to request promotion yet. "
                    f"You can submit /promote on {eligible_at.strftime('%Y-%m-%d %H:%M %Z')}."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(PromoteModal(self.bot, application_record))

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id or str(payload.emoji) not in ("✅", "❌"):
            return

        guild, member, message = await self._fetch_review_message(payload)
        if guild is None or member is None or message is None or not message.embeds:
            return

        if not member.guild_permissions.manage_roles:
            return

        embed = message.embeds[0]
        marker_type, marker_values = parse_footer_marker(embed.footer.text)
        if marker_type != PROMOTION_REQUEST_MARKER:
            return

        current_status = get_embed_field(embed, "Status")
        if current_status != "In Review":
            return

        applicant_id = marker_values.get("user_id") or get_embed_field(embed, "Discord ID")
        if not applicant_id:
            return

        applicant = guild.get_member(int(applicant_id))
        if applicant is None:
            try:
                applicant = await guild.fetch_member(int(applicant_id))
            except discord.NotFound:
                return

        new_embed = embed.copy()
        status_value = (
            f"Approved by {member.display_name}"
            if str(payload.emoji) == "✅"
            else f"Denied by {member.display_name}"
        )
        new_embed.color = (
            discord.Color.green() if str(payload.emoji) == "✅" else discord.Color.red()
        )
        replace_embed_field(new_embed, "Status", status_value, inline=False)
        new_embed.set_footer(
            text=build_footer_text(PROMOTION_REQUEST_MARKER, user_id=applicant.id),
            icon_url=SERVER_ICON,
        )

        if str(payload.emoji) == "✅":
            employee_role = get_employee_role(guild)
            intern_role = get_intern_role(guild)
            if employee_role is None or intern_role is None:
                return

            await applicant.add_roles(
                employee_role,
                reason=f"Promotion request approved by {member}",
            )
            if intern_role in applicant.roles:
                await applicant.remove_roles(
                    intern_role,
                    reason=f"Promotion request approved by {member}",
                )

        await message.edit(embed=new_embed)
        await message.clear_reactions()

        try:
            if str(payload.emoji) == "✅":
                await applicant.send(
                    "Your promotion request was approved. You have been promoted to Employee."
                )
            else:
                await applicant.send(
                    "Your promotion request was denied by staff."
                )
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Promote(bot))
