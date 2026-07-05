from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord
import time
import aiohttp
from datetime import datetime, timedelta, timezone

from application_utils import execute_supabase
from config import SERVER_ICON

REPORT_COOLDOWN = 600  # seconds


async def _get_roblox_headshot(username: str) -> str | None:
    """Return a Roblox headshot URL for the given username, or None on failure."""
    try:
        url = f"https://www.roblox.com/users/profile?username={username}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True) as resp:
                parts = str(resp.url).split("/")
                if len(parts) <= 4:
                    return None
                roblox_id = parts[4]
            async with session.get(
                f"https://thumbnails.roblox.com/v1/users/avatar-headshot"
                f"?userIds={roblox_id}&size=420x420&format=Png"
            ) as resp:
                data = await resp.json()
                return data["data"][0]["imageUrl"]
    except Exception:
        return None

GUILD_ID = int(os.getenv("GUILDID"))
REPORT_CHANNEL = "teamer-reports"
REPORT_BAN_ROLE = "Teamer Banned"
REPORT_PING_ROLE = 992939084760748032


class ClockInButton(discord.ui.Button):
    def __init__(self, report_id, roblox_link):
        super().__init__(
            label="Clock In",
            style=discord.ButtonStyle.green,
            custom_id=f"join_report:{report_id}",
        )
        self.report_id = report_id
        self.roblox_link = roblox_link

    def _link_view(self):
        v = discord.ui.View()
        v.add_item(discord.ui.Button(
            label="Open ROBLOX",
            style=discord.ButtonStyle.link,
            url=self.roblox_link,
        ))
        return v

    async def callback(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        supabase = interaction.client.supabase
        response = await execute_supabase(
            supabase.rpc("join_report", {
                "report_id": self.report_id,
                "user_id": interaction.user.id,
            })
        )
        result = response.data

        if result["already_joined"]:
            await interaction.edit_original_response(
                content=(
                    "You've already clocked in to this report."
                ),
                view=self._link_view(),
            )
            return

        self.view.clocked_in.add(interaction.user.id)

        await interaction.edit_original_response(
            content="You're clocked in. Make sure to clock out when the report ends to receive credit.",
            view=self._link_view(),
        )


class ClockOutButton(discord.ui.Button):
    def __init__(self, report_id, caller_id):
        super().__init__(
            label="Clock Out",
            style=discord.ButtonStyle.primary,
            custom_id=f"clock_out:{report_id}",
        )
        self.report_id = report_id
        self.caller_id = caller_id

    async def callback(self, interaction: Interaction):
        if interaction.user.id not in self.view.clocked_in:
            await interaction.response.send_message(
                "You didn't clock in to this report.", ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        self.view.clocked_in.discard(interaction.user.id)
        self.view.clocked_out.append(interaction.user.mention)

        supabase = interaction.client.supabase
        await execute_supabase(
            supabase.rpc("award_report_credit", {"user_id": interaction.user.id})
        )

        await interaction.edit_original_response(
            content="Clocked out. Your service is appreciated.",
        )


class ClockOutView(discord.ui.View):
    def __init__(self, report_id, caller_id, clocked_in: set):
        super().__init__(timeout=300)
        self.clocked_in = clocked_in
        self.clocked_out: list[str] = []
        self.message = None
        self.add_item(ClockOutButton(report_id, caller_id))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                if self.clocked_out:
                    credit_list = "\n".join(self.clocked_out)
                    content = f"~~Clock out period has ended.~~\n\n**Members receiving report credit:**\n{credit_list}"
                else:
                    content = "~~Clock out period has ended.~~ No members clocked out."
                await self.message.edit(content=content, view=self)
            except Exception:
                pass


class EndButton(discord.ui.Button):
    def __init__(self, report_id, caller_id):
        super().__init__(
            label="End Report",
            style=discord.ButtonStyle.red,
            custom_id=f"end_report:{report_id}",
        )
        self.report_id = report_id
        self.caller_id = caller_id

    async def callback(self, interaction: Interaction):
        if (interaction.user.id != self.caller_id
                and not interaction.user.guild_permissions.manage_events):
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return

        await interaction.response.defer()
        supabase = interaction.client.supabase
        await execute_supabase(
            supabase.rpc("end_report", {"report_id": self.report_id})
        )

        clocked_in = self.view.clocked_in.copy()

        old = interaction.message.embeds[0]
        ended = discord.Embed(
            title="REPORT ENDED",
            color=discord.Color.dark_grey(),
        )
        for f in old.fields:
            ended.add_field(name=f.name, value=f.value, inline=f.inline)
        if old.thumbnail:
            ended.set_thumbnail(url=old.thumbnail.url)
        if old.footer:
            ended.set_footer(text=old.footer.text, icon_url=old.footer.icon_url)

        for child in self.view.children:
            child.disabled = True
        await interaction.message.edit(embed=ended, view=self.view)

        if clocked_in:
            clock_out_view = ClockOutView(self.report_id, self.caller_id, clocked_in)
            clock_out_msg = await interaction.followup.send(
                f"To get credit for the report with <@{self.caller_id}>, make sure to clock out.",
                view=clock_out_view,
                wait=True,
            )
            clock_out_view.message = clock_out_msg

        if hasattr(interaction.client, "active_reports"):
            interaction.client.active_reports.pop(self.report_id, None)


class ReportView(discord.ui.View):
    def __init__(self, report_id, caller_id, roblox_link):
        super().__init__(timeout=None)
        self.clocked_in = set()
        self.add_item(ClockInButton(report_id, roblox_link))
        self.add_item(EndButton(report_id, caller_id))


class ReportModal(discord.ui.Modal):
    def __init__(self, bot, cooldowns: dict):
        super().__init__(title="Teamer Report", timeout=None)
        self.bot = bot
        self.supabase = bot.supabase
        self._cooldowns = cooldowns
        self.roblox_link = discord.ui.TextInput(
            label="Roblox Link",
            placeholder="https://www.roblox.com/users/...",
            max_length=200, required=True,
        )
        self.enemies = discord.ui.TextInput(
            label="Enemies",
            placeholder="Must have 3 or more enemies to call a report. Put each enemy name on a separate line.",
            style=discord.TextStyle.paragraph,
            max_length=500, required=True,
        )
        self.notes = discord.ui.TextInput(
            label="Notes", style=discord.TextStyle.paragraph,
            max_length=200, required=False,
        )
        for item in (self.roblox_link, self.enemies, self.notes):
            self.add_item(item)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        response = await execute_supabase(self.supabase.rpc("check_reports_lock"))
        lock_data = response.data
        if lock_data and lock_data.get("is_locked"):
            locked_until = lock_data.get("locked_until")
            if locked_until:
                dt = datetime.fromisoformat(locked_until.replace("Z", "+00:00"))
                ts = int(dt.timestamp())
                await interaction.edit_original_response(
                    content=f"Reports are locked until <t:{ts}:R>.",
                )
            else:
                await interaction.edit_original_response(
                    content="Reports are currently locked indefinitely.",
                )
            return

        ban_role = discord.utils.get(interaction.guild.roles, name=REPORT_BAN_ROLE)
        if ban_role and ban_role in interaction.user.roles:
            await interaction.edit_original_response(
                content="You are banned from making reports.",
            )
            return

        link = self.roblox_link.value.strip()
        if not (link.startswith("https://www.roblox.com/") or link.startswith("https://roblox.com/")):
            await interaction.edit_original_response(
                content="Invalid Roblox link. Must start with `https://www.roblox.com/` or `https://roblox.com/`.",
            )
            return

        enemy_lines = [line.strip() for line in self.enemies.value.split("\n") if line.strip()]
        if len(enemy_lines) < 3:
            await interaction.edit_original_response(
                content="Must have 3 or more enemies to call a report.",
            )
            return

        notes_val = self.notes.value.strip() if self.notes.value else None
        report_num = (await execute_supabase(
            self.supabase.rpc("reserve_report_id")
        )).data

        # All checks passed; lock in the cooldown now.
        if interaction.user.name != "larnagack":
            self._cooldowns[interaction.user.id] = time.time()

        report_response = await execute_supabase(
            self.supabase.rpc("create_report", {
                "p_id": report_num,
                "caller_id": interaction.user.id,
                "game": "",
                "roblox_link": link,
                "enemies": self.enemies.value,
                "notes": notes_val,
                "channel_id": interaction.channel_id,
            })
        )
        report_row = report_response.data

        report_id = report_row[0]["id"]

        # Roblox headshot; falls back to Discord avatar if lookup fails.
        thumbnail_url = interaction.user.display_avatar.url
        stats_response = await execute_supabase(
            self.supabase.rpc("fetchstats", params={"uid": interaction.user.id})
        )
        stats_data = stats_response.data
        if stats_data and stats_data.get("username"):
            headshot = await _get_roblox_headshot(stats_data["username"])
            if headshot:
                thumbnail_url = headshot

        embed = discord.Embed(
            title=f"{interaction.user.display_name} - TEAMER REPORT",
            color=discord.Color.red(),
        )
        embed.add_field(name=f"INCIDENT #{report_id}", value="", inline=False)
        embed.add_field(name="CALLER", value=f"<@{interaction.user.id}>", inline=False)
        embed.add_field(name="OPPONENTS", value="", inline=False)
        embed.add_field(name="​", value="\n".join(enemy_lines), inline=False)
        if notes_val:
            embed.add_field(name="NOTES", value=notes_val, inline=False)
        embed.set_thumbnail(url=thumbnail_url)
        embed.set_footer(
            text="Custom Adversaries Association",
            icon_url=SERVER_ICON,
        )

        view = ReportView(report_id, interaction.user.id, link)

        channel = interaction.guild.get_channel(interaction.channel_id)
        message = await channel.send(embed=embed, view=view)
        await channel.send(content=f"<@&{REPORT_PING_ROLE}>")

        await execute_supabase(
            self.supabase.rpc("set_report_message", {
                "report_id": report_id,
                "message_id": message.id,
            })
        )

        if not hasattr(self.bot, "active_reports"):
            self.bot.active_reports = {}
        self.bot.active_reports[report_id] = view
        await interaction.edit_original_response(content="Report submitted.")


class Report(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase
        self._cooldowns: dict[int, float] = {}

    @app_commands.command(name="report", description="Call a teamer report.")
    @app_commands.guilds(Object(id=GUILD_ID))
    async def report(self, interaction: Interaction):
        if interaction.user.name != "larnagack":
            now = time.time()
            last = self._cooldowns.get(interaction.user.id, 0.0)
            remaining = REPORT_COOLDOWN - (now - last)
            if remaining > 0:
                retry_ts = int(now + remaining)
                await interaction.response.send_message(
                    f"You can call a report again <t:{retry_ts}:R>.", ephemeral=True,
                )
                return

        if "teamer" not in interaction.channel.name.lower():
            await interaction.response.send_message(
                "This command can only be used in a teamer support channel.", ephemeral=True,
            )
            return

        ban_role = discord.utils.get(interaction.guild.roles, name=REPORT_BAN_ROLE)
        if ban_role and ban_role in interaction.user.roles:
            await interaction.response.send_message(
                "You are banned from making reports.", ephemeral=True,
            )
            return

        await interaction.response.send_modal(ReportModal(self.bot, self._cooldowns))

    @app_commands.command(name="lockreports", description="Lock reports globally or for a single user.")
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    @app_commands.describe(
        user="Optional. Bans this user from making reports.",
        time_minutes="Optional. If omitted, the lock/ban is permanent until manually undone.",
    )
    async def lockreports(
        self, interaction: Interaction,
        user: discord.Member = None,
        time_minutes: int = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if user is None:
            if time_minutes is not None:
                locked_until = (
                    datetime.now(timezone.utc) + timedelta(minutes=time_minutes)
                ).isoformat()
            else:
                locked_until = None
            await execute_supabase(
                self.supabase.rpc("lock_reports", {"locked_until": locked_until})
            )
            if time_minutes:
                await interaction.edit_original_response(
                    content=f"Reports locked for {time_minutes} minute(s).",
                )
            else:
                await interaction.edit_original_response(
                    content="Reports locked indefinitely.",
                )
        else:
            ban_role = discord.utils.get(interaction.guild.roles, name=REPORT_BAN_ROLE)
            if ban_role:
                await user.add_roles(ban_role, reason=f"Report banned by {interaction.user}")
            if time_minutes is not None:
                expires_at = (
                    datetime.now(timezone.utc) + timedelta(minutes=time_minutes)
                ).isoformat()
                await execute_supabase(
                    self.supabase.rpc("ban_user_report", {
                        "user_id": user.id,
                        "expires_at": expires_at,
                    })
                )
                await interaction.edit_original_response(
                    content=f"{user.mention} is banned from reports for {time_minutes} minute(s).",
                )
            else:
                await interaction.edit_original_response(
                    content=f"{user.mention} is permanently banned from reports.",
                )

    @app_commands.command(name="unlockreports", description="Unlock reports globally or for a single user.")
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    @app_commands.describe(user="Optional. Removes this user's report ban.")
    async def unlockreports(self, interaction: Interaction, user: discord.Member = None):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if user is None:
            await execute_supabase(self.supabase.rpc("unlock_reports"))
            await interaction.edit_original_response(content="Reports unlocked.")
        else:
            ban_role = discord.utils.get(interaction.guild.roles, name=REPORT_BAN_ROLE)
            if ban_role and ban_role in user.roles:
                await user.remove_roles(ban_role, reason=f"Report ban removed by {interaction.user}")
            await execute_supabase(
                self.supabase.rpc("unban_user_report", {"user_id": user.id})
            )
            await interaction.edit_original_response(
                content=f"{user.mention}'s report ban has been removed.",
            )


async def setup(bot):
    await bot.add_cog(Report(bot))
