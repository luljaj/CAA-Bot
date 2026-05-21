from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord
from datetime import datetime, timedelta, timezone

GUILD_ID = int(os.getenv("GUILDID"))
REPORT_CHANNEL = "teamer-reports"
REPORT_BAN_ROLE = "Report Banned"
CAA_ICON = "https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024"


class JoinButton(discord.ui.Button):
    def __init__(self, report_id, roblox_link):
        super().__init__(
            label="Join Report",
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
                "You've already joined this report.",
                view=self._link_view(), ephemeral=True,
            )
            return

        embed = interaction.message.embeds[0]
        old_icon = embed.footer.icon_url if embed.footer else None
        embed.set_footer(
            text=f"{result['participant_count']} members joined · Custom Adversaries Association",
            icon_url=old_icon,
        )
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(
            "You've joined! Stay until the end for credit.",
            view=self._link_view(), ephemeral=True,
        )


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
        participants = supabase.rpc(
            "end_report", {"report_id": self.report_id}
        ).execute().data or []

        mentions = []
        for p in participants:
            m = interaction.guild.get_member(p["user_id"])
            mentions.append(m.mention if m else f"`{p['user_id']}` (left server)")

        old = interaction.message.embeds[0]
        ended = discord.Embed(
            title="✅ Report Ended",
            description=old.description,
            color=discord.Color.dark_grey(),
        )
        for f in old.fields:
            ended.add_field(name=f.name, value=f.value, inline=f.inline)
        ended.add_field(
            name=f"Participants ({len(mentions)})",
            value="\n".join(mentions) if mentions else "None",
            inline=False,
        )
        if old.footer:
            ended.set_footer(text=old.footer.text, icon_url=old.footer.icon_url)

        for child in self.view.children:
            child.disabled = True
        await interaction.response.edit_message(embed=ended, view=self.view)

        if mentions:
            await interaction.followup.send(
                f"Participants for staff credit: {', '.join(mentions)}"
            )

        if hasattr(interaction.client, "active_reports"):
            interaction.client.active_reports.pop(self.report_id, None)


class ReportView(discord.ui.View):
    def __init__(self, report_id, caller_id, roblox_link):
        super().__init__(timeout=None)
        self.add_item(JoinButton(report_id, roblox_link))
        self.add_item(EndButton(report_id, caller_id))


class ReportModal(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Teamer Report", timeout=None)
        self.bot = bot
        self.supabase = bot.supabase
        self.game = discord.ui.TextInput(
            label="Game", placeholder="e.g. MM2, Blade Ball",
            max_length=50, required=True,
        )
        self.roblox_link = discord.ui.TextInput(
            label="Roblox Link",
            placeholder="https://www.roblox.com/games/...",
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
        for item in (self.game, self.roblox_link, self.enemies, self.notes):
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

        active = self.supabase.rpc("get_active_report", {"game": self.game.value}).execute().data
        if active:
            await interaction.response.send_message(
                f"An active report for **{self.game.value}** already exists.", ephemeral=True,
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
            "game": self.game.value,
            "roblox_link": link,
            "enemies": self.enemies.value,
            "notes": notes_val,
            "channel_id": interaction.channel_id,
        }).execute().data

        report_id = report_row["id"]

        embed = discord.Embed(
            title="⚠️ Teamer Report",
            description=f"Link: {link}",
            color=discord.Color.red(),
        )
        embed.add_field(name="Game", value=self.game.value, inline=True)
        embed.add_field(name="Enemies", value="\n".join(enemy_lines), inline=False)
        if notes_val:
            embed.add_field(name="Notes", value=notes_val, inline=False)
        embed.add_field(name="Called By", value=f"<@{interaction.user.id}>", inline=False)
        embed.set_footer(
            text="0 members joined · Custom Adversaries Association",
            icon_url=CAA_ICON,
        )

        view = ReportView(report_id, interaction.user.id, link)

        await interaction.response.send_message("Report submitted.", ephemeral=True)
        message = await interaction.channel.send(embed=embed, view=view)

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

    @app_commands.command(name="report", description="Call a teamer report.")
    @app_commands.guilds(Object(id=GUILD_ID))
    async def report(self, interaction: Interaction):
        if interaction.channel.name != REPORT_CHANNEL:
            await interaction.response.send_message(
                f"This command can only be used in #{REPORT_CHANNEL}.", ephemeral=True,
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
