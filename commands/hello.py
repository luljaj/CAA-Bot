from discord.ext import commands
from discord import app_commands, Interaction, Object
import os

GUILD_ID = int(os.getenv("GUILDID"))

class Hello(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="hello", description="Say hi!")
    @app_commands.guilds(Object(id=GUILD_ID))  # 👈 This is key
    async def hello(self, interaction: Interaction):
        await interaction.response.send_message("Hey there!")

async def setup(bot):
    await bot.add_cog(Hello(bot))
