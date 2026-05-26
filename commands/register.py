from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import re
import discord
from datetime import datetime
from zoneinfo import ZoneInfo

from config import ENTRY_REVIEW_CHANNEL_ID, SERVER_ICON, get_intern_role
from review_utils import (
    REGISTER_REQUEST_MARKER,
    build_footer_text,
    get_embed_field,
    parse_footer_marker,
    replace_embed_field,
)

GUILD_ID = int(os.getenv("GUILDID"))


def _extract_user_id(value: str | None) -> int | None:
    if not value:
        return None

    match = re.search(r"(\d{5,})", value)
    if not match:
        return None

    return int(match.group(1))

class FrontDoor(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Front Door", timeout=None)
        self.bot = bot
        self.supabase = bot.supabase
        
        self.username = discord.ui.TextInput(
            label='Roblox Username',
            placeholder='Enter your Roblox name',
            max_length=20,
            required=True
        )
        self.reason = discord.ui.TextInput(
            label='Reason for Entry',
            placeholder='Why do you want to join?',
            style=discord.TextStyle.paragraph,
            max_length=150,
            required=True
        )
        self.inviter = discord.ui.TextInput(
            label='Referrer',
            placeholder='Who invited you or how did you find us?',
            max_length=25,
            required=True
        )

        self.add_item(self.username)
        self.add_item(self.reason)
        self.add_item(self.inviter)

    async def on_submit(self, interaction: Interaction):
        self.supabase.rpc(
            "register",
            params={
                "uid": interaction.user.id,
                "u": self.username.value,
                "r": self.reason.value,
                "inv": self.inviter.value
            }
        ).execute()

        await interaction.response.send_message(
            "Thank you for your application to the CAA.",
            ephemeral=True
        )

        # Prepare embed message
        now = datetime.now(ZoneInfo("America/New_York"))
        formatted = now.strftime("%Y-%m-%d %H:%M")

        embed = discord.Embed(
            title="🛎️ Entry Request",
            description=f"Submission at {formatted}",
            color=5647104
        )
        embed.add_field(name="Discord User", value=f"<@{interaction.user.id}>", inline=False)
        embed.add_field(name="Discord ID", value=str(interaction.user.id), inline=False)
        embed.add_field(name="Roblox User", value=self.username.value, inline=True)
        embed.add_field(name="Stated Intent", value=self.reason.value, inline=False)
        embed.add_field(name="Referrer", value=self.inviter.value or "N/A", inline=False)
        embed.add_field(name="Status", value="In Review", inline=False)
        embed.set_footer(
            text=build_footer_text(REGISTER_REQUEST_MARKER, user_id=interaction.user.id),
            icon_url=SERVER_ICON
        )


        channel = self.bot.get_channel(ENTRY_REVIEW_CHANNEL_ID)
        if channel is None:
            channel = await self.bot.fetch_channel(ENTRY_REVIEW_CHANNEL_ID)
        message = await channel.send(embed=embed)

        await message.add_reaction('✅')
        await message.add_reaction('❌')

class Register(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="register", description="Fill out a form to apply.")
    @app_commands.guilds(Object(id=GUILD_ID))
    async def register_modal(self, interaction: Interaction):
        if interaction.channel.name == "the-front-door":
            await interaction.response.send_modal(FrontDoor(self.bot))
        else:
            await interaction.response.send_message('You are already in.', ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id or str(payload.emoji) not in ('✅', '❌'):
            return

        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return

        member = payload.member or guild.get_member(payload.user_id)
        if not member or not member.guild_permissions.manage_roles:
            return

        channel = guild.get_channel(payload.channel_id)
        if channel is None:
            fetched = await self.bot.fetch_channel(payload.channel_id)
            channel = fetched if isinstance(fetched, discord.TextChannel) else None
        if channel is None:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return
        if not message.embeds:
            return

        old_embed = message.embeds[0]
        marker_type, marker_values = parse_footer_marker(old_embed.footer.text)
        if marker_type != REGISTER_REQUEST_MARKER and old_embed.title != "🛎️ Entry Request":
            return

        if get_embed_field(old_embed, "Status") != "In Review":
            return

        applicant_id = (
            _extract_user_id(marker_values.get("user_id"))
            or _extract_user_id(get_embed_field(old_embed, "Discord ID"))
            or _extract_user_id(get_embed_field(old_embed, "Discord User"))
        )
        rbluser = get_embed_field(old_embed, "Roblox User")
        if not applicant_id:
            return

        applicant = guild.get_member(applicant_id)
        if applicant is None:
            try:
                applicant = await guild.fetch_member(applicant_id)
            except discord.NotFound:
                return

        new_embed = old_embed.copy()
        new_embed.color = (
            discord.Color.green() if str(payload.emoji) == '✅' else discord.Color.red()
        )
        status_value = (
            f"Approved by {member.display_name}"
            if str(payload.emoji) == '✅'
            else f"Denied by {member.display_name}"
        )
        replace_embed_field(new_embed, "Status", status_value, inline=False)
        replace_embed_field(new_embed, "Discord ID", str(applicant.id), inline=False)
        new_embed.set_footer(
            text=build_footer_text(REGISTER_REQUEST_MARKER, user_id=applicant.id),
            icon_url=SERVER_ICON
        )

        if str(payload.emoji) == '✅':
            intern_role = get_intern_role(guild)
            if intern_role is None:
                return

            await applicant.add_roles(intern_role, reason=f'Promoted by {member}')
            if rbluser:
                try:
                    await applicant.edit(nick=rbluser)
                except discord.HTTPException:
                    pass

        await message.edit(embed=new_embed)
        await message.clear_reactions()

        if str(payload.emoji) == '✅':
            await channel.send(f'<@{applicant.id}> ({rbluser}) has been promoted to Intern.')
        else:
            await channel.send(f'<@{applicant.id}> has been denied.')

async def setup(bot):
    await bot.add_cog(Register(bot))
