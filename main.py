import discord  
import os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv("TOKEN")

class Client(discord.Client):
    async def on_ready(self):
        print(f'Started as {self.user}')

    async def on_message(self,message):
        print(f'{message.author}: {message.content}')

intents = discord.Intents.default()
intents.message_content = True

client = Client(intents=intents)

client.run(token)