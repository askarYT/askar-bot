import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
"""import logging"""

"""logging.basicConfig(level=logging.INFO)"""


load_dotenv()
token = os.getenv('ASKAR_TOKEN')

class MyBot(commands.Bot):
    async def setup_hook(self):
        for extension in ['random','ping','mimir','poke','sun','xp_system','youtube']:
            await self.load_extension(f'cogs.{extension}')
            print(f'Loaded: cogs.{extension}')

            """logging.info(f'Loaded: cogs.{extension}')"""
    async def on_ready(self):
        await bot.tree.sync()
        print(f'Lancé en tant que {self.user} !' + 'Version "discord.py": {discord.__version__}')
        """await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name =f"{bot.command_prefix}help"))"""
        """logging.info(f'Lancé en tant que {self.user} !')"""
        """logging.info(f"discord.py version: {discord.__version__}")"""
        

intents = discord.Intents.all()
bot = MyBot(command_prefix='.', intents=intents)

bot.run(token=token)