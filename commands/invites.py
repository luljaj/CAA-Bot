from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

GUILD_ID = int(os.getenv("GUILDID"))


class Invites(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(
        name="invites",
        description="View list of people a user has invited."
    )
    @app_commands.guilds(Object(id=GUILD_ID))
    async def invites(self, interaction: Interaction, user: discord.User):
        await interaction.response.defer(thinking=True)

        invite_count = 0
        invite_count_resp = (
            self.supabase.rpc("get_user_invite_count", params={"uid": user.id})
            .execute()
        )
        if invite_count_resp.data:
            count_data = (
                invite_count_resp.data[0]
                if isinstance(invite_count_resp.data, list)
                else invite_count_resp.data
            )
            if isinstance(count_data, dict):
                invite_count = count_data.get("invite_count", 0) or 0

        invitees_resp = (
            self.supabase.rpc("get_user_invitees", params={"uid": user.id, "lim": 10})
            .execute()
        )
        invitees = (
            invitees_resp.data
            if isinstance(invitees_resp.data, list)
            else [invitees_resp.data] if invitees_resp.data else []
        )

        lines = []
        for row in invitees:
            if not isinstance(row, dict):
                continue
            discord_id = row.get("discord_id")
            roblox_username = row.get("roblox_username") or "Unknown"
            mention = f"<@{discord_id}>" if discord_id else "Unknown"
            lines.append(f"- {mention} ({roblox_username})")

        if not lines:
            lines = ["No invites found."]

        embed = discord.Embed(
            title=f"RECRUITMENT RECORD - {user.name}",
            description=f"TOTAL RECRUITS: {invite_count}",
            color=user.top_role.color if user.top_role else discord.Color.dark_gray()
        )
        embed.add_field(name="MEMBERS RECRUITED", value="\n".join(lines), inline=False)
        embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
        embed.set_footer(
            text='Custom Adversaries Association',
            icon_url='https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024'
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Invites(bot))
