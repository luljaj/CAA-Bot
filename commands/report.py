from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord
import time
from datetime import datetime, timedelta, timezone

REPORT_COOLDOWN = 600  # seconds

GUILD_ID = int(os.getenv("GUILDID"))
REPORT_CHANNEL = "teamer-reports"
REPORT_BAN_ROLE = "Teamer Banned"
REPORT_PING_ROLE = 992939084760748032
CAA_ICON = "https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024"


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
        supabase = interaction.client.supabase
        result = supabase.rpc("join_report", {
            "report_id": self.report_id,
            "user_id": interaction.user.id,
        }).execute().data

        if result["already_joined"]:
            await interaction.response.send_message(
                "You've already clocked in to this report.",
                view=self._link_view(), ephemeral=True,
            )
            return

        self.view.clocked_in.add(interaction.user.id)

        embed = interaction.message.embeds[0]
        old_icon = embed.footer.icon_url if embed.footer else None
        embed.set_footer(
            text=f"{result['participant_count']} clocked in · Custom Adversaries Association",
            icon_url=old_icon,
        )
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(
            "You're clocked in! Make sure to clock out when the report ends to receive credit.",
            view=self._link_view(), ephemeral=True,
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

        self.view.clocked_in.discard(interaction.user.id)

        supabase = interaction.client.supabase
        supabase.rpc("award_report_credit", {"user_id": interaction.user.id}).execute()

        await interaction.response.send_message(
            "Clocked out! Your report credit has been recorded.", ephemeral=True,
        )


class ClockOutView(discord.ui.View):
    def __init__(self, report_id, caller_id, clocked_in: set):
        super().__init__(timeout=300)
        self.clocked_in = clocked_in
        self.message = None
        self.add_item(ClockOutButton(report_id, caller_id))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    content="~~Clock out period has ended.~~",
                    view=self,
                )
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

        supabase = interaction.client.supabase
        supabase.rpc("end_report", {"report_id": self.report_id}).execute()

        clocked_in = self.view.clocked_in.copy()

        old = interaction.message.embeds[0]
        ended = discord.Embed(
            title="✅ REPORT ENDED",
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
        await interaction.response.edit_message(embed=ended, view=self.view)

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
    def __init__(self, bot):
        super().__init__(title="Teamer Report", timeout=None)
        self.bot = bot
        self.supabase = bot.supabase
        self.roblox_link = discord.ui.TextInput(
            label="Roblox Link",
            placeholder="https://www.roblox.com/users/...",
            max_length=200, required=True,
        )
        self.enemies = discord.ui.TextInput(
            label="Enemies",
            placeholder="Must have 3 or more enemies to call a report",
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
        lock_data = self.supabase.rpc("check_reports_lock").execute().data
        if lock_data and lock_data.get("is_locked"):
            locked_until = lock_data.get("locked_until")
            if locked_until:
                dt = datetime.fromisoformat(locked_until.replace("Z", "+00:00"))
                ts = int(dt.timestamp())
                await interaction.response.send_message(
                    f"Reports are locked until <t:{ts}:R>.", ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Reports are currently locked indefinitely.", ephemeral=True,
                )
            return

        ban_role = discord.utils.get(interaction.guild.roles, name=REPORT_BAN_ROLE)
        if ban_role and ban_role in interaction.user.roles:
            await interaction.response.send_message(
                "You are banned from making reports.", ephemeral=True,
            )
            return

        link = self.roblox_link.value.strip()
        if not (link.startswith("https://www.roblox.com/") or link.startswith("https://roblox.com/")):
            await interaction.response.send_message(
                "Invalid Roblox link. Must start with `https://www.roblox.com/` or `https://roblox.com/`.",
                ephemeral=True,
            )
            return

        enemy_lines = [line.strip() for line in self.enemies.value.split("\n") if line.strip()]
        if len(enemy_lines) < 3:
            await interaction.response.send_message(
                "Must have 3 or more enemies to call a report.", ephemeral=True,
            )
            return

        notes_val = self.notes.value.strip() if self.notes.value else None

        report_row = self.supabase.rpc("create_report", {
            "caller_id": interaction.user.id,
            "game": "",
            "roblox_link": link,
            "enemies": self.enemies.value,
            "notes": notes_val,
            "channel_id": interaction.channel_id,
        }).execute().data

        report_id = report_row["id"]

        embed = discord.Embed(
            title=f"⚠️ {interaction.user.display_name} - TEAMER REPORT",
            color=discord.Color.red(),
        )
        embed.add_field(name="INCIDENT FILE", value="", inline=False)
        embed.add_field(name="CALLER", value=f"<@{interaction.user.id}>", inline=True)
        embed.add_field(name="LINK", value=link, inline=True)
        embed.add_field(name="OPPONENTS", value="", inline=False)
        embed.add_field(name="​", value="\n".join(enemy_lines), inline=False)
        if notes_val:
            embed.add_field(name="NOTES", value=notes_val, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(
            text="0 clocked in · Custom Adversaries Association",
            icon_url=CAA_ICON,
        )

        view = ReportView(report_id, interaction.user.id, link)

        await interaction.response.send_message("Report submitted.", ephemeral=True)
        message = await interaction.channel.send(
            content=f"<@&{REPORT_PING_ROLE}>",
            embed=embed,
            view=view,
        )

        self.supabase.rpc("set_report_message", {
            "report_id": report_id,
            "message_id": message.id,
        }).execute()

        if not hasattr(self.bot, "active_reports"):
            self.bot.active_reports = {}
        self.bot.active_reports[report_id] = view


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
            self._cooldowns[interaction.user.id] = now

        if "teamer" not in interaction.channel.name.lower():
            await interaction.response.send_message(
                "This command can only be used in a teamer support channel.", ephemeral=True,
            )
            return

        lock_data = self.supabase.rpc("check_reports_lock").execute().data
        if lock_data and lock_data.get("is_locked"):
            locked_until = lock_data.get("locked_until")
            if locked_until:
                dt = datetime.fromisoformat(locked_until.replace("Z", "+00:00"))
                ts = int(dt.timestamp())
                await interaction.response.send_message(
                    f"Reports are locked until <t:{ts}:R>.", ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Reports are currently locked indefinitely.", ephemeral=True,
                )
            return

        ban_role = discord.utils.get(interaction.guild.roles, name=REPORT_BAN_ROLE)
        if ban_role and ban_role in interaction.user.roles:
            await interaction.response.send_message(
                "You are banned from making reports.", ephemeral=True,
            )
            return

        await interaction.response.send_modal(ReportModal(self.bot))

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
        if user is None:
            if time_minutes is not None:
                locked_until = (
                    datetime.now(timezone.utc) + timedelta(minutes=time_minutes)
                ).isoformat()
            else:
                locked_until = None
            self.supabase.rpc("lock_reports", {"locked_until": locked_until}).execute()
            if time_minutes:
                await interaction.response.send_message(
                    f"Reports locked for {time_minutes} minute(s).", ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Reports locked indefinitely.", ephemeral=True,
                )
        else:
            ban_role = discord.utils.get(interaction.guild.roles, name=REPORT_BAN_ROLE)
            if ban_role:
                await user.add_roles(ban_role, reason=f"Report banned by {interaction.user}")
            if time_minutes is not None:
                expires_at = (
                    datetime.now(timezone.utc) + timedelta(minutes=time_minutes)
                ).isoformat()
                self.supabase.rpc("ban_user_report", {
                    "user_id": user.id,
                    "expires_at": expires_at,
                }).execute()
                await interaction.response.send_message(
                    f"{user.mention} is banned from reports for {time_minutes} minute(s).",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"{user.mention} is permanently banned from reports.", ephemeral=True,
                )

    @app_commands.command(name="unlockreports", description="Unlock reports globally or for a single user.")
    @app_commands.default_permissions(manage_events=True)
    @app_commands.guilds(Object(id=GUILD_ID))
    @app_commands.describe(user="Optional. Removes this user's report ban.")
    async def unlockreports(self, interaction: Interaction, user: discord.Member = None):
        if user is None:
            self.supabase.rpc("unlock_reports").execute()
            await interaction.response.send_message("Reports unlocked.", ephemeral=True)
        else:
            ban_role = discord.utils.get(interaction.guild.roles, name=REPORT_BAN_ROLE)
            if ban_role and ban_role in user.roles:
                await user.remove_roles(ban_role, reason=f"Report ban removed by {interaction.user}")
            self.supabase.rpc("unban_user_report", {"user_id": user.id}).execute()
            await interaction.response.send_message(
                f"{user.mention}'s report ban has been removed.", ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(Report(bot))
