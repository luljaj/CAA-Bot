from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord
from datetime import datetime
from config import SERVER_ICON

GUILD_ID = int(os.getenv("GUILDID"))


def _fmt_ts(iso_str, style="F"):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return f"<t:{int(dt.timestamp())}:{style}>"
    except Exception:
        return iso_str


class Strikes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase

    @app_commands.command(name="strike", description="Issue a strike to a user.")
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    @app_commands.describe(
        user="The user to strike.",
        reason="The reason for the strike.",
        count="Number of strikes to issue (default: 1).",
        duration_days="Override the default strike duration in days.",
    )
    async def strike(
        self, interaction: Interaction,
        user: discord.Member,
        reason: str,
        count: int = 1,
        duration_days: int = None,
    ):
        if count < 1:
            await interaction.response.send_message("Count must be at least 1.", ephemeral=True)
            return
        if duration_days is not None and not (1 <= duration_days <= 3650):
            await interaction.response.send_message(
                "Duration must be between 1 and 3650 days.", ephemeral=True,
            )
            return

        row = self.supabase.rpc("add_strike", {
            "user_id": user.id,
            "reason": reason,
            "count": count,
            "issued_by": interaction.user.id,
            "duration_days": duration_days,
        }).execute().data

        active_strikes = self.supabase.rpc("get_strikes", {"user_id": user.id}).execute().data or []
        total_active = sum(s.get("count", 1) for s in active_strikes)

        embed = discord.Embed(title="Strike Issued", color=discord.Color.orange())
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Count", value=str(count), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Expires", value=_fmt_ts(row.get("expires_at", ""), "F"), inline=True)
        embed.add_field(name="Issued By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Total Active Strikes", value=str(total_active), inline=True)
        embed.set_footer(text="Custom Adversaries Association", icon_url=SERVER_ICON)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unstrike", description="Remove a user's most recent active strike.")
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    @app_commands.describe(user="The user whose most recent strike should be removed.")
    async def unstrike(self, interaction: Interaction, user: discord.Member):
        removed = self.supabase.rpc("remove_latest_strike", {
            "user_id": user.id,
        }).execute().data

        if not removed:
            await interaction.response.send_message(
                f"{user.mention} has no active strikes to remove.",
                ephemeral=True,
            )
            return

        active_strikes = self.supabase.rpc("get_strikes", {"user_id": user.id}).execute().data or []
        total_active = sum(s.get("count", 1) for s in active_strikes)

        embed = discord.Embed(title="Strike Removed", color=discord.Color.green())
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Removed Count", value=str(removed.get("count", 1)), inline=True)
        embed.add_field(name="Removed By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=removed.get("reason", "N/A"), inline=False)
        embed.add_field(
            name="Originally Issued",
            value=_fmt_ts(removed.get("created_at", ""), "F"),
            inline=True,
        )
        embed.add_field(name="Total Active Strikes", value=str(total_active), inline=True)
        embed.set_footer(text="Custom Adversaries Association", icon_url=SERVER_ICON)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="strikes", description="View a user's active strikes.")
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    async def strikes(self, interaction: Interaction, user: discord.Member):
        all_strikes = self.supabase.rpc("get_strikes", {"user_id": user.id}).execute().data or []

        total = len(all_strikes)
        shown = all_strikes[:15]

        embed = discord.Embed(
            title=f"Strikes — {user.display_name}",
            color=discord.Color.orange(),
        )

        if not shown:
            embed.description = "No active strikes."
        else:
            if total > 15:
                embed.description = f"Showing 15 of {total} active strikes."
            for s in shown:
                issued_display = _fmt_ts(s.get("created_at", ""), "D")
                expires_display = _fmt_ts(s.get("expires_at", ""), "R")
                issuer_id = s.get("issued_by")
                issuer = f"<@{issuer_id}>" if issuer_id else "Unknown"
                count = s.get("count", 1)
                embed.add_field(
                    name=f"Strike · {issued_display} · ×{count}",
                    value=(
                        f"**Reason:** {s.get('reason', 'N/A')}\n"
                        f"**Issued by:** {issuer}\n"
                        f"**Expires:** {expires_display}"
                    ),
                    inline=False,
                )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setstrikeduration", description="Set the default strike duration in days.")
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    async def setstrikeduration(self, interaction: Interaction, days: int):
        if not (1 <= days <= 3650):
            await interaction.response.send_message(
                "Duration must be between 1 and 3650 days.", ephemeral=True,
            )
            return
        self.supabase.rpc("set_strike_duration", {"days": days}).execute()
        await interaction.response.send_message(
            f"Default strike duration is now {days} days. Existing strikes are unaffected.",
            ephemeral=True,
        )

    @app_commands.command(name="strikeduration", description="View the current default strike duration.")
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    async def strikeduration(self, interaction: Interaction):
        data = self.supabase.rpc("get_strike_duration").execute().data
        days = data.get("default_duration_days", "?") if data else "?"
        await interaction.response.send_message(
            f"Default strike duration: **{days} days**.", ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Strikes(bot))
