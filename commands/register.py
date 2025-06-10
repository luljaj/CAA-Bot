from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord
from datetime import datetime
from zoneinfo import ZoneInfo

GUILD_ID = int(os.getenv("GUILDID"))
REVIEW_CHANNEL = 1356017239039414615
INTERN_ID = 992605675949666315
FRONTDOOR_ID = 986110301722251334


class FrontDoor(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Front Door", timeout=None)
        self.bot = bot
        self.supabase = bot.supabase
        
        username = discord.ui.TextInput(
            label='Roblox Username',
            placeholder='Enter your Roblox name',
            max_length=20,
            required=True
        )
        reason = discord.ui.TextInput(
            label='Reason for Entry',
            placeholder='Why do you want to join?',
            style=discord.TextStyle.paragraph,
            max_length=150,
            required=True
        )
        inviter = discord.ui.TextInput(
            label='Referrer',
            placeholder='Who invited you or how did you find us?',
            max_length=25,
            required=True
        )

        self.add_item(username)
        self.add_item(reason)
        self.add_item(inviter)
  
        self.username = username
        self.reason = reason
        self.inviter = inviter

        username = username
        reason = reason
        inviter = inviter

    async def on_submit(self, interaction: Interaction):

        response =  (
        self.supabase.rpc("register", params = {"uid":interaction.user.id, "u" :self.username.value, "r":self.reason.value, "inv":self.inviter.value})
        .execute()
            )

        await interaction.response.send_message(
            f"Thank you for your application to the CAA.",
            ephemeral=True
        )

        now = datetime.now(ZoneInfo("America/New_York"))
        formatted = now.strftime("%Y-%m-%d %H:%M")

        formatted = now.strftime("%Y-%m-%d %H:%M")  # Date then hour:minute

        embed = discord.Embed(
                    title="🛎️ Entry Request",
                    description=f"Submission at {formatted}",
                    color=(5647104)
                )
        embed.add_field(name="Discord User", value=f"<@{interaction.user.id}>", inline=False)
        embed.add_field(name="Roblox User", value=self.username.value, inline=True)
        embed.add_field(name="Stated Intent", value=self.reason.value, inline=False)
        embed.add_field(name="Referrer", value=self.inviter.value or "N/A", inline=False)
        embed.set_footer(text = 'Custom Adversaries Association', icon_url='https://cdn.discordapp.com/icons/938810131800543333/a5572ec6502690f351ab956dd5a67d8e.png?size=1024')

        class ReviewMenu(discord.ui.View):
            def __init__(self,user,rbluser,bot):
                super().__init__()
                self.user = user
                self.bot = bot
                self.rbluser = rbluser
            @discord.ui.button(label='Approve', style=discord.ButtonStyle.green)
            async def on_approval(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
                self.stop()
                await interaction.response.send_message(content=f'<@{self.user.id}> ({self.rbluser}) has been promoted to Intern.')
                intern = discord.utils.get(interaction.guild.roles, name="Intern")
                await self.user.add_roles(intern, reason = f'Promoted by <@{interaction.user.id}>')
                await self.user.edit(nick=self.rbluser)


            @discord.ui.button(label='Deny', style=discord.ButtonStyle.red)
            async def on_denial(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
                self.stop()
                await interaction.response.send_message(content=f'<@{self.user.id}> has been denied.')


        channel = self.bot.get_channel(REVIEW_CHANNEL)
        await channel.send(embed = embed, view = ReviewMenu(interaction.user,self.username.value,self.bot))

class Register(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="register", description="Fill out a form to apply.")
    @app_commands.guilds(Object(id=GUILD_ID))
    async def register_modal(self, interaction: Interaction):
        if interaction.channel.name == "the-front-door":
            await interaction.response.send_modal(FrontDoor(self.bot))
        else:
            await interaction.response.send_message(f'You are already in.', ephemeral= True)


async def setup(bot):
    await bot.add_cog(Register(bot))
