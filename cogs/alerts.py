import discord
import os
import re
import json
import requests # type: ignore
from discord import app_commands
from discord.ext import commands, tasks
from discord.utils import get
from pymongo import MongoClient  # type: ignore
from twitchAPI.twitch import Twitch # type: ignore

import aiohttp
from datetime import datetime, timedelta

# 
class Alerts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = MongoClient(os.getenv("MONGO_URI"))
        self.db = self.client["askar_bot"]
        self.alerts_collection = self.db["alerts"]
        self.youtube_last_video = {}
        self.youtube_notif_times = {}  # <<<< Ajout pour anti-flood
        self.twitch_access_token = None
        self.twitch_live_notified = {}
        self.session = aiohttp.ClientSession()
        self.check_alerts.start()
        log("Cog 'Alerts' initialisé.", self.bot)


# Initialisation des logs
LOG_CHANNEL_ID = 1367923588786552862  # Remplace par l'ID du salon de logs Discord

def log(message, bot=None):
    now = datetime.now().strftime("%d-%m-%Y | %H-%M-%S-%f")
    formatted_message = f"[{now}] {message}"

    if bot:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            bot.loop.create_task(channel.send(formatted_message))
    else:
        print(formatted_message)

# Identification des API
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

# Identification de Twitch
twitch = Twitch(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)
twitch.authenticate_app([])
TWITCH_STREAM_API_ENDPOINT_V5 = "https://api.twitch.tv/kraken/streams/{}"
API_HEADERS = {
    'Client-ID': TWITCH_CLIENT_ID,
    'Accept': 'application/vnd.twitchtv.v5+json',
}

if not (YOUTUBE_API_KEY and TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET):
    log("Clés API manquantes dans les variables d'environnement.", self.bot)

    @app_commands.command(name="alerts", description="Afficher les alertes et les utilisateurs inscrits")
    @app_commands.checks.has_permissions(administrator=True)
    async def alert(self, interaction: discord.Interaction):
        log(f"Commande '/alerts' exécutée par {interaction.user}.", self.bot)
        alerts = list(self.alerts_collection.find())

        if not alerts:
            await interaction.response.send_message("Aucune alerte enregistrée.")
            log("Aucune alerte trouvée.", self.bot)
            return

        alert_message = "Liste des alertes inscrites :\n"
        for alert in alerts:
            platform = "YouTube" if alert.get("channel_id") else "Twitch"
            channel_identifier = alert.get("channel_id") or alert.get("twitch_username")

            content_types = ', '.join(alert["types"])
            alert_message += f"\n**{platform}** : {channel_identifier}\n"
            alert_message += f"  - Types de contenu : {content_types}\n"

            for content_type, role_id in alert["notif_roles"].items():
                role = interaction.guild.get_role(role_id) if role_id else "Aucun rôle défini"
                alert_message += f"  - Rôle pour `{content_type}` : {role}\n"

        await interaction.response.send_message(alert_message)

    @app_commands.command(name="alerts-add", description="Ajouter une alerte")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_alert(self, interaction: discord.Interaction, platform: str, channel_identifier: str, content_type: str):
        log(f"Commande '/alerts-add' exécutée par {interaction.user}.", self.bot)
        platform = platform.lower()
        content_type = content_type.lower()

        if platform not in ["youtube", "twitch"]:
            log(f"Plateforme invalide: {platform}", self.bot)
            return await interaction.response.send_message("❌ Plateforme invalide (youtube ou twitch).")
        if content_type not in ["video", "short", "live", "tiktok"]:
            log(f"Type de contenu invalide: {content_type}", self.bot)
            return await interaction.response.send_message("❌ Type de contenu invalide.")

        query = {"channel_id" if platform == "youtube" else "twitch_username": channel_identifier}
        alert = self.alerts_collection.find_one(query)

        if alert:
            if content_type not in alert["types"]:
                self.alerts_collection.update_one(
                    {"_id": alert["_id"]},
                    {"$push": {"types": content_type}}
                )
                await interaction.response.send_message(f"✅ Contenu `{content_type}` ajouté pour {channel_identifier}.")
                log(f"Contenu `{content_type}` ajouté pour {channel_identifier}.", self.bot)
            else:
                self.alerts_collection.update_one(
                    {"_id": alert["_id"]},
                    {"$pull": {"types": content_type}}
                )
                await interaction.response.send_message(f"❌ Contenu `{content_type}` retiré pour {channel_identifier}.")
                log(f"Contenu `{content_type}` retiré pour {channel_identifier}.", self.bot)
        else:
            new_alert = {
                "channel_id": channel_identifier if platform == "youtube" else None,
                "twitch_username": channel_identifier if platform == "twitch" else None,
                "types": [content_type],
                "notif_roles": {
                    "video": None,
                    "short": None,
                    "live": None,
                    "tiktok": None
                },
                "target_channel_id": None,
                "owner": interaction.user.id
            }
            self.alerts_collection.insert_one(new_alert)
            await interaction.response.send_message(f"🎉 Nouvelle alerte créée pour {channel_identifier} ({content_type}).")
            log(f"Nouvelle alerte créée pour {channel_identifier} ({content_type}).", self.bot)

    @app_commands.command(name="alerts-set-role", description="Définir un rôle pour une alerte")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_role(self, interaction: discord.Interaction, platform: str, channel_identifier: str, content_type: str, role: discord.Role):
        log(f"Commande '/alerts-set-role' exécutée par {interaction.user}.", self.bot)
        platform = platform.lower()
        content_type = content_type.lower()

        if content_type not in ["video", "short", "live", "tiktok"]:
            log(f"Type invalide: {content_type}", self.bot)
            return await interaction.response.send_message("❌ Type invalide.")

        query = {"channel_id" if platform == "youtube" else "twitch_username": channel_identifier}
        alert = self.alerts_collection.find_one(query)

        if not alert:
            log(f"Alerte non trouvée pour {channel_identifier}.", self.bot)
            return await interaction.response.send_message("❌ Cette alerte n'existe pas.")

        self.alerts_collection.update_one(
            {"_id": alert["_id"]},
            {"$set": {f"notif_roles.{content_type}": role.id}}
        )

        await interaction.response.send_message(f"🔔 Rôle pour `{content_type}` mis à jour.")
        log(f"Rôle pour `{content_type}` mis à jour pour {channel_identifier}.", self.bot)

    @app_commands.command(name="alerts-set-channel", description="Définir le salon des notifications pour une alerte")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, platform: str, channel_identifier: str, channel: discord.TextChannel):
        log(f"Commande '/alerts-set-channel' exécutée par {interaction.user}.", self.bot)
        platform = platform.lower()

        query = {"channel_id" if platform == "youtube" else "twitch_username": channel_identifier}
        alert = self.alerts_collection.find_one(query)

        if not alert:
            log(f"Alerte non trouvée pour {channel_identifier}.", self.bot)
            return await interaction.response.send_message("❌ Cette alerte n'existe pas.")

        self.alerts_collection.update_one(
            {"_id": alert["_id"]},
            {"$set": {"target_channel_id": channel.id}}
        )

        await interaction.response.send_message(f"📢 Salon de notification mis à jour.")
        log(f"Salon de notification mis à jour pour {channel_identifier}.", self.bot)

    """""
    async def check_twitch(self, alert):
        if not self.twitch_access_token:
            await self.refresh_twitch_token()

        username = alert["twitch_username"]
        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {self.twitch_access_token}"
        }
        url = f"https://api.twitch.tv/helix/streams?user_login={username}"

        async with self.session.get(url, headers=headers) as response:
            data = await response.json()

        is_live = bool(data.get("data"))
        target_channel_id = alert.get("target_channel_id")
        if not target_channel_id:
            return

        channel = self.bot.get_channel(target_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        if is_live:
            if self.twitch_live_notified.get(username):
                return
            self.twitch_live_notified[username] = True

            role_id = alert.get("notif_roles", {}).get("live")
            role_mention = f"<@&{role_id}>" if role_id else ""

            await channel.send(f"{role_mention} **{username} est en LIVE !** 🎥\nhttps://twitch.tv/{username}")
            log(f"[Twitch] {username} vient de lancer un live.", self.bot)
        else:
            self.twitch_live_notified[username] = False

    async def refresh_twitch_token(self):
        url = f"https://id.twitch.tv/oauth2/token?client_id={TWITCH_CLIENT_ID}&client_secret={TWITCH_CLIENT_SECRET}&grant_type=client_credentials"
        async with self.session.post(url) as response:
            data = await response.json()
            self.twitch_access_token = data["access_token"]
            log("[Twitch] Nouveau token d'accès récupéré.", self.bot)
    """""


async def setup(bot):
    await bot.add_cog(Alerts(bot))
