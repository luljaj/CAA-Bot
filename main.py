import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from supabase import Client, create_client
import logging



load_dotenv()
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILDID"))
SUPAURL = str(os.getenv('SUPABASE_DB_URL'))
SUPAKEY = str(os.getenv('SUPABASE_KEY'))

supabase: Client = create_client(SUPAURL,SUPAKEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="1241243235234234234234",intents=intents)

bot.supabase = supabase

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def setup_hook():
    # "edit" was renamed to "editevents"; skip it if the old file still exists on disk
    _skip = {"edit"}
    for filename in os.listdir("./commands"):
        if filename.endswith(".py") and filename[:-3] not in _skip:
            await bot.load_extension(f"commands.{filename[:-3]}")

    await bot.load_extension("cogs.frontdoorcleaner")
    await bot.load_extension("cogs.expirycleaner")
    await bot.load_extension("cogs.promotionalerts")

    bot.active_reports = {}
    from commands.report import ReportView
    active = supabase.rpc("get_all_active_reports").execute().data or []
    for r in active:
        view = ReportView(r["id"], r["caller_id"], r["roblox_link"])
        bot.add_view(view, message_id=r["message_id"])
        bot.active_reports[r["id"]] = view

    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)

bot.run(TOKEN, log_level=logging.DEBUG, root_logger=True)
