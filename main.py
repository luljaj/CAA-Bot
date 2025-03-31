import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILDID"))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="1241243235234234234234",intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def setup_hook():
    for filename in os.listdir("./commands"):
        if filename.endswith(".py"):
            await bot.load_extension(f"commands.{filename[:-3]}")

    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)

bot.run(TOKEN)
