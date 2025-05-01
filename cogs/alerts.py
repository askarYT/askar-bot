import discord
from discord.ext import commands, tasks
from pymongo import MongoClient
from bson import ObjectId
import aiohttp
import os
from discord import app_commands

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")  # Clé API YouTube
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

class Alerts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = MongoClient(os.getenv("MONGO_URI"))
        self.db = self.client["askar_bot"]  # Nom de ta base Mongo
        self.alerts_collection = self.db["alerts"]
        self.youtube_last_video = {}  # cache temporaire
        self.twitch_access_token = None
        self.check_alerts.start()

    def cog_unload(self):
        self.check_alerts.cancel()

    # PERMISSION : admin only
    async def cog_check(self, ctx):
        return ctx.author.guild_permissions.administrator

    @app_commands.command(name="alert", description="Gérer les alertes")
    async def alert(self, interaction: discord.Interaction):
        await interaction.response.send_message("Sous-commandes : `add`, `set-role`, `set-channel`")

    @app_commands.command(name="add", description="Ajouter une alerte")
    async def add_alert(self, interaction: discord.Interaction, platform: str, channel_identifier: str, content_type: str):
        platform = platform.lower()
        content_type = content_type.lower()

        if platform not in ["youtube", "twitch"]:
            return await interaction.response.send_message("❌ Plateforme invalide (youtube ou twitch).")
        
        if content_type not in ["video", "short", "live", "tiktok"]:
            return await interaction.response.send_message("❌ Type de contenu invalide.")

        query = {"channel_id" if platform == "youtube" else "twitch_username": channel_identifier}
        alert = self.alerts_collection.find_one(query)

        if alert:
            if content_type not in alert["types"]:
                self.alerts_collection.update_one(
                    {"_id": ObjectId(alert["_id"])}),
                {"$push": {"types": content_type}}
                
                await interaction.response.send_message(f"✅ Contenu `{content_type}` ajouté pour {channel_identifier}.")
            else:
                self.alerts_collection.update_one(
                    {"_id": ObjectId(alert["_id"])}),
                {"$pull": {"types": content_type}}
                
                await interaction.response.send_message(f"❌ Contenu `{content_type}` retiré pour {channel_identifier}.")
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

    @app_commands.command(name="set-role", description="Définir un rôle pour une alerte")
    async def set_role(self, interaction: discord.Interaction, platform: str, channel_identifier: str, content_type: str, role: discord.Role):
        platform = platform.lower()
        content_type = content_type.lower()

        if content_type not in ["video", "short", "live", "tiktok"]:
            return await interaction.response.send_message("❌ Type invalide.")

        query = {"channel_id" if platform == "youtube" else "twitch_username": channel_identifier}
        alert = self.alerts_collection.find_one(query)

        if not alert:
            return await interaction.response.send_message("❌ Cette alerte n'existe pas.")

        self.alerts_collection.update_one(
            {"_id": ObjectId(alert["_id"])}),
        {"$set": {f"notif_roles.{content_type}": role.id}}
        
        await interaction.response.send_message(f"🔔 Rôle pour `{content_type}` mis à jour.")

    @app_commands.command(name="set-channel", description="Définir le salon des notifications pour une alerte")
    async def set_channel(self, interaction: discord.Interaction, platform: str, channel_identifier: str, channel: discord.TextChannel):
        platform = platform.lower()

        query = {"channel_id" if platform == "youtube" else "twitch_username": channel_identifier}
        alert = self.alerts_collection.find_one(query)

        if not alert:
            return await interaction.response.send_message("❌ Cette alerte n'existe pas.")

        self.alerts_collection.update_one(
            {"_id": ObjectId(alert["_id"])}),
        {"$set": {"target_channel_id": channel.id}}
        
        await interaction.response.send_message(f"📢 Salon de notification mis à jour.")

    @tasks.loop(minutes=5)
    async def check_alerts(self):
        alerts = self.alerts_collection.find()

        for alert in alerts:
            if alert.get("channel_id"):  # YouTube
                await self.check_youtube(alert)

            if alert.get("twitch_username"):  # Twitch
                await self.check_twitch(alert)

    async def check_youtube(self, alert):
        channel_id = alert["channel_id"]
        types = alert["types"]
        url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id&order=date&maxResults=1"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()

        if "items" not in data:
            return

        latest = data["items"][0]
        video_id = latest["id"].get("videoId")
        if not video_id:
            return

        # éviter de spammer la même vidéo
        if self.youtube_last_video.get(channel_id) == video_id:
            return
        self.youtube_last_video[channel_id] = video_id

        video_title = latest["snippet"]["title"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # Détecter short ou vidéo normale
        is_short = "shorts" in latest["snippet"]["title"].lower()

        if (is_short and "short" not in types) or (not is_short and "video" not in types):
            return

        # Envoi notif
        guild = self.bot.get_guild(alert["target_channel_id"] >> 22)  # hack pour obtenir guild_id depuis channel_id
        if not guild:
            return

        channel = guild.get_channel(alert["target_channel_id"])
        if not channel:
            return

        role_id = alert["notif_roles"]["short" if is_short else "video"]
        role_mention = f"<@&{role_id}>" if role_id else ""

        await channel.send(f"{role_mention} Nouvelle {'Short' if is_short else 'Vidéo'} !\n{video_title}\n{video_url}")

    async def check_twitch(self, alert):
        if not self.twitch_access_token:
            await self.refresh_twitch_token()

        username = alert["twitch_username"]
        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {self.twitch_access_token}"
        }
        url = f"https://api.twitch.tv/helix/streams?user_login={username}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                data = await response.json()

        if data.get("data"):
            stream = data["data"][0]
            guild = self.bot.get_guild(alert["target_channel_id"] >> 22)
            if not guild:
                return

            channel = guild.get_channel(alert["target_channel_id"])
            if not channel:
                return

            role_id = alert["notif_roles"]["live"]
            role_mention = f"<@&{role_id}>" if role_id else ""

            await channel.send(f"{role_mention} **{username} est en LIVE !** 🎥\nhttps://twitch.tv/{username}")

    async def refresh_twitch_token(self):
        url = f"https://id.twitch.tv/oauth2/token?client_id={TWITCH_CLIENT_ID}&client_secret={TWITCH_CLIENT_SECRET}&grant_type=client_credentials"
        async with aiohttp.ClientSession() as session:
            async with session.post(url) as response:
                data = await response.json()
                self.twitch_access_token = data["access_token"]

async def setup(bot):
    await bot.add_cog(Alerts(bot))
