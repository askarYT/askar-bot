import os
import discord
import requests
from discord.ext import commands, tasks
from discord import app_commands
from pymongo import MongoClient
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

client = MongoClient(os.getenv("MONGO_URI"))
db = client["youtube_notify_db"]
collection = db["youtube_channels"]

class YouTubeNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.checkforvideos.start()

    @tasks.loop(seconds=30)
    async def checkforvideos(self):
        print("Now Checking!")

        for doc in collection.find():
            youtube_channel_id = doc["_id"]
            channel_name = doc["channel_name"]
            latest_url = doc.get("latest_video_url", "none")
            discord_channel_id = doc["notifying_discord_channel"]
            video_role_id = doc.get("video_role_id")
            short_role_id = doc.get("short_role_id")  # on utilise bien "short_role_id"

            feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={youtube_channel_id}"
            response = requests.get(feed_url)

            if response.status_code != 200:
                print(f"Erreur lors de la récupération du flux pour {channel_name}")
                continue

            root = ET.fromstring(response.text)
            entry = root.find("{http://www.w3.org/2005/Atom}entry")
            if entry is None:
                continue

            video_url = entry.find("{http://www.w3.org/2005/Atom}link").attrib["href"]
            published_str = entry.find("{http://www.w3.org/2005/Atom}published").text
            published_time = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%S%z")
            now = datetime.now(timezone.utc)

            time_diff = (now - published_time).total_seconds()

            # On envoie si la vidéo est nouvelle ou s'il n'y avait pas encore de vidéo en base, et si elle est récente (moins de 5 min)
            if (latest_url == "none" or video_url != latest_url) and time_diff <= 300:
                print(f"Nouvelle vidéo détectée : {video_url}")
                collection.update_one(
                    {"_id": youtube_channel_id},
                    {"$set": {"latest_video_url": video_url}}
                )

                discord_channel = self.bot.get_channel(int(discord_channel_id))
                if not discord_channel:
                    print(f"Salon introuvable pour l’ID {discord_channel_id}")
                    continue

                # Détection shorts avec "/shorts/" dans l'URL (tu peux raffiner plus tard)
                is_short = "/shorts/" in video_url

                if is_short:
                    role_mention = f"<@&{short_role_id}>" if short_role_id else "@everyone"
                    msg = f"{role_mention} {channel_name} a publié un nouveau **Short** ! 🎬\n{video_url}"
                else:
                    role_mention = f"<@&{video_role_id}>" if video_role_id else "@everyone"
                    msg = f"{role_mention} {channel_name} a publié une nouvelle **vidéo** ! 📹\n{video_url}"

                await discord_channel.send(msg)
            else:
                print(f"Aucune nouvelle vidéo récente pour {channel_name} (diff: {int(time_diff)}s)")

    @app_commands.command(name="add_youtube_notification_data", description="Ajoute une chaîne YouTube à surveiller.")
    async def add_youtube_notification_data(self, interaction: discord.Interaction, channel_id: str, channel_name: str):
        existing = collection.find_one({"_id": channel_id})

        if existing:
            await interaction.response.send_message("❌ Cette chaîne est déjà suivie.", ephemeral=True)
            return

        data = {
            "_id": channel_id,
            "channel_name": channel_name,
            "latest_video_url": "none",
            "notifying_discord_channel": str(interaction.channel_id),
            "video_role_id": None,
            "short_role_id": None
        }

        collection.insert_one(data)
        await interaction.response.send_message("✅ Chaîne ajoutée avec succès !", ephemeral=True)

    @app_commands.command(name="set_youtube_roles", description="Définit les rôles à mentionner pour les vidéos et les shorts.")
    async def set_youtube_roles(self, interaction: discord.Interaction, channel_id: str, video_role: discord.Role = None, short_role: discord.Role = None):
        result = collection.find_one({"_id": channel_id})
        if not result:
            await interaction.response.send_message("❌ Chaîne non trouvée dans la base de données.", ephemeral=True)
            return

        update_data = {}
        if video_role:
            update_data["video_role_id"] = str(video_role.id)
        if short_role:
            update_data["short_role_id"] = str(short_role.id)

        if update_data:
            collection.update_one({"_id": channel_id}, {"$set": update_data})
            await interaction.response.send_message("✅ Rôles mis à jour avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Aucun rôle fourni à mettre à jour.", ephemeral=True)

    async def cog_unload(self):
        self.checkforvideos.cancel()

async def setup(bot):
    await bot.add_cog(YouTubeNotifier(bot))
