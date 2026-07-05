import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from supabase import Client, create_client
import logging
import json
import time


def _agent_log(run_id, hypothesis_id, location, message, data=None):
    try:
        payload = {
            "sessionId": "fd2be3",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with open("/Users/lukauljaj/CAA-Bot/.cursor/debug-fd2be3.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


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
    #region agent log
    _agent_log("pre-fix", "H4", "main.py:on_ready", "on_ready reached", {"bot_user": str(bot.user)})
    #endregion
    print(f"Logged in as {bot.user}",flush=True)

@bot.event
async def setup_hook():
    #region agent log
    _agent_log("pre-fix", "H1,H2,H3,H4", "main.py:setup_hook", "setup_hook started")
    #endregion
    # "edit" was renamed to "editevents"; skip it if the old file still exists on disk
    _skip = {"edit"}
    for filename in os.listdir("./commands"):
        if filename.endswith(".py") and filename[:-3] not in _skip:
            extension = f"commands.{filename[:-3]}"
            try:
                if extension == "commands.report":
                    #region agent log
                    _agent_log("pre-fix", "H1,H2", "main.py:setup_hook", "report extension load starting")
                    #endregion
                await bot.load_extension(extension)
                if extension == "commands.report":
                    #region agent log
                    _agent_log("pre-fix", "H1,H2", "main.py:setup_hook", "report extension loaded")
                    #endregion
            except Exception as exc:
                #region agent log
                _agent_log("pre-fix", "H1,H2", "main.py:setup_hook", "extension load failed", {"extension": extension, "error": repr(exc), "error_type": type(exc).__name__})
                #endregion
                raise

    for extension in ("cogs.frontdoorcleaner", "cogs.expirycleaner", "cogs.promotionalerts"):
        try:
            await bot.load_extension(extension)
        except Exception as exc:
            #region agent log
            _agent_log("pre-fix", "H1,H2", "main.py:setup_hook", "extension load failed", {"extension": extension, "error": repr(exc), "error_type": type(exc).__name__})
            #endregion
            raise
    #region agent log
    _agent_log("pre-fix", "H1,H2", "main.py:setup_hook", "cog extensions loaded")
    #endregion

    bot.active_reports = {}
    from commands.report import ReportView
    try:
        #region agent log
        _agent_log("pre-fix", "H3", "main.py:setup_hook", "active report restore starting")
        #endregion
        active = supabase.rpc("get_all_active_reports").execute().data or []
        #region agent log
        _agent_log("pre-fix", "H3", "main.py:setup_hook", "active report restore rpc returned", {"row_count": len(active), "data_type": type(active).__name__})
        #endregion
    except Exception as exc:
        #region agent log
        _agent_log("pre-fix", "H3", "main.py:setup_hook", "active report restore failed", {"error": repr(exc), "error_type": type(exc).__name__})
        #endregion
        raise
    for r in active:
        view = ReportView(r["id"], r["caller_id"], r["roblox_link"])
        bot.add_view(view, message_id=r["message_id"])
        bot.active_reports[r["id"]] = view

    guild = discord.Object(id=GUILD_ID)
    #region agent log
    _agent_log("pre-fix", "H4", "main.py:setup_hook", "tree sync starting", {"guild_id": GUILD_ID})
    #endregion
    await bot.tree.sync(guild=guild)
    #region agent log
    _agent_log("pre-fix", "H4", "main.py:setup_hook", "setup_hook completed")
    #endregion

bot.run(TOKEN, log_level=logging.DEBUG, root_logger=True)
