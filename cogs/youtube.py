import json
import requests
import re
import os

import discord
from discord.ext import commands, tasks
from discord import app_commands
from pymongo import MongoClient

# Connexion à MongoDB
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
            short_role_id = doc.get("short_role_id")

            print(f"Now Checking For {channel_name}")
            channel_url = f"https://www.youtube.com/channel/{youtube_channel_id}"
            html = requests.get(channel_url + "/videos").text

            try:
                latest_video_url = "https://www.youtube.com/watch?v=" + re.search('(?<="videoId":").*?(?=")', html).group()
            except:
                continue

            if latest_url != latest_video_url:
                collection.update_one(
                    {"_id": youtube_channel_id},
                    {"$set": {"latest_video_url": latest_video_url}}
                )

                discord_channel = self.bot.get_channel(int(discord_channel_id))
                if not discord_channel:
                    print(f"⚠️ Canal Discord introuvable : {discord_channel_id}")
                    continue

                is_short = "/shorts/" in latest_video_url

                if is_short:
                    role_mention = f"<@&{short_role_id}>" if short_role_id else "@everyone"
                    msg = f"{role_mention} {channel_name} a publié un nouveau **Short** ! 🎬\n{latest_video_url}"
                else:
                    role_mention = f"<@&{video_role_id}>" if video_role_id else "@everyone"
                    msg = f"{role_mention} {channel_name} a publié une nouvelle **vidéo** ! 📹\n{latest_video_url}"

                await discord_channel.send(msg)

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
            "notifying_discord_channel": "1367923588786552862",
            "video_role_id": None,
            "short_role_id": None
        }

        collection.insert_one(data)
        await interaction.response.send_message("✅ Chaîne ajoutée à la base de données MongoDB !", ephemeral=True)

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

# Fonction pour ajouter le COG
async def setup(bot):
    await bot.add_cog(YouTubeNotifier(bot))
