from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord
from datetime import datetime
from zoneinfo import ZoneInfo

GUILD_ID = int(os.getenv("GUILDID"))
REVIEW_CHANNEL = 1382493785400934410
INTERN_ROLE_NAME = "Intern"

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
            required=False  # Make it optional
        )
        self.add_item(self.username)
        self.add_item(self.reason)
        self.add_item(self.inviter)

    async def on_submit(self, interaction: Interaction):
        # Store in OLD inviter column (text)
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
        embed.add_field(name="Roblox User", value=self.username.value, inline=True)
        embed.add_field(name="Stated Intent", value=self.reason.value, inline=False)
        embed.add_field(
            name="Referrer",
            value=self.inviter.value or "N/A",
            inline=False
        )
        embed.add_field(name="Status", value="In Review", inline=False)
        embed.set_footer(text='Custom Adversaries Association', icon_url=interaction.guild.icon.url if interaction.guild.icon else None)


        channel = self.bot.get_channel(REVIEW_CHANNEL)
        message = await channel.send(embed=embed)

        await message.add_reaction('✅')
        await message.add_reaction('❌')

        bot = self.bot
        if not hasattr(bot, 'pending_reviews'):
            bot.pending_reviews = {}
        bot.pending_reviews[message.id] = {
            'applicant': interaction.user,
            'rbluser': self.username.value
        }

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
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):

        if user.bot:
            return

        message_id = reaction.message.id
        bot = self.bot
        if not hasattr(bot, 'pending_reviews') or message_id not in bot.pending_reviews:
            return


        if reaction.emoji not in ('✅', '❌'):
            return

        guild = reaction.message.guild
        member = guild.get_member(user.id)

        if not member or (not member.guild_permissions.manage_roles and member.name != 'larnagack'):

            return

        data = bot.pending_reviews.pop(message_id)
        applicant = data['applicant']
        rbluser = data['rbluser']
        review_channel = reaction.message.channel

  
        old_embed = reaction.message.embeds[0]

        new_embed = discord.Embed(
            title=old_embed.title,
            description=old_embed.description,
            color=old_embed.color
        )
        for field in old_embed.fields:
            if field.name == "Status":
                status_value = f"Approved by {member.name}" if reaction.emoji == '✅' else f"Denied by {member.name}"
                new_embed.add_field(name="Status", value=status_value, inline=False)
            else:
                new_embed.add_field(name=field.name, value=field.value, inline=field.inline)
        new_embed.set_footer(text=old_embed.footer.text, icon_url=old_embed.footer.icon_url)


        await reaction.message.edit(embed=new_embed)
  
        await reaction.message.clear_reactions()


        if reaction.emoji == '✅':
            intern_role = discord.utils.get(guild.roles, name=INTERN_ROLE_NAME)
            await applicant.add_roles(intern_role, reason=f'Promoted by {user}')
            await applicant.edit(nick=rbluser)
            await review_channel.send(f'<@{applicant.id}> ({rbluser}) has been promoted to Intern.')
        else:
            await review_channel.send(f'<@{applicant.id}> has been denied.')

async def setup(bot):
    await bot.add_cog(Register(bot))
