from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import sqlite3
import discord

db_folder = './databases'
db_file = os.path.join(db_folder, 'applications.db')
GUILD_ID = int(os.getenv("GUILDID"))
REVIEW_CHANNEL = 1356017239039414615
INTERN_ID = 1356349048516382781


class FrontDoor(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Front Door", timeout=None)
        self.bot = bot

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
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO applications (discordid, username, reason, inviter)
            VALUES (?, ?, ?, ?)
            ''', (
                interaction.user.id,
                self.username.value,
                self.reason.value,
                self.inviter.value
            ))
            conn.commit()
            applicant = interaction.user.id

        await interaction.response.send_message(
            f"Thank you for your application to the CAA.",
            ephemeral=True
        )

        embed = discord.Embed(
                    title="🛎️ Front Door Application",
                    color=(5647104)
                )
        embed.add_field(name="Discord User", value=f"<@{interaction.user.id}>", inline=False)
        embed.add_field(name="Roblox Username", value=self.username.value, inline=True)
        embed.add_field(name="Reason for Entry", value=self.reason.value, inline=False)
        embed.add_field(name="Referrer", value=self.inviter.value or "N/A", inline=False)

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
                await self.user.add_roles(intern)
                await self.user.edit(nick=self.rbluser)
            @discord.ui.button(label='Deny', style=discord.ButtonStyle.red)
            async def on_denial(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
                self.stop()
                await interaction.response.send_message(content=f'<@{self.user.id}> has been denied and kicked.')


        channel = self.bot.get_channel(REVIEW_CHANNEL)
        await channel.send(embed = embed, view = ReviewMenu(interaction.user,self.username.value,self.bot))


class Register(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="register", description="Fill out a form to apply.")
    @app_commands.guilds(Object(id=GUILD_ID))
    async def register_modal(self, interaction: Interaction):
        await interaction.response.send_modal(FrontDoor(self.bot))


async def setup(bot):
    await bot.add_cog(Register(bot))
