import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
import logging
from logging.handlers import RotatingFileHandler

# --- Configuration avancée du logging ---
# 1. Créer le logger principal
logger = logging.getLogger()
logger.setLevel(logging.INFO) # Niveau de log minimal à traiter

# 2. Créer un formateur pour uniformiser le style des logs
log_format = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s', datefmt='%d-%m-%Y %H:%M:%S')

# 3. Créer un handler pour la console (ce que tu vois dans PuTTY)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_format)
logger.addHandler(console_handler)

# 4. Créer un handler pour les fichiers rotatifs (pour l'historique)
# Crée jusqu'à 5 fichiers de 5MB chacun.
file_handler = RotatingFileHandler('bot.log', maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(log_format)
logger.addHandler(file_handler)

load_dotenv()
token = os.getenv('ASKAR_TOKEN')


class MyBot(commands.Bot):
    async def setup_hook(self):
        for extension in ['random','ping','mimir','poke','sun','xp_system','notifications.youtube_notifier', 'notifications.twitch_notifier', 'twitch_follower']:
            await self.load_extension(f'cogs.{extension}')
            logging.info(f'Loaded: cogs.{extension}')

    async def on_ready(self):
        await bot.tree.sync()
        logging.info(f'STARTING BOT !')
        try:
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name =f"{bot.command_prefix}help"))
        except:
            logging.warning(f"Le status discord ne s'est pas initialisé correctement...")

        logging.info(f'Lancé en tant que {self.user} !')
        logging.info(f'Version de discord.py: {discord.__version__}')
        

intents = discord.Intents.all()
bot = MyBot(command_prefix='.', intents=intents)

bot.run(token, log_handler=None) # On désactive le handler par défaut de discord.py car on a le nôtre