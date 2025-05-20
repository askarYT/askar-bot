import json
import requests
import re
import os

import discord
from discord.ext import commands, tasks
from discord import app_commands
from pymongo import MongoClient

# Connexion à MongoDB
client = MongoClient(os.getenv("MONGO_URI"))  # Mets ton URI ici
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
                msg = f"@everyone {channel_name} a sorti une nouvelle vidéo ou est en live : {latest_video_url}"
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
            "notifying_discord_channel": str(interaction.channel_id)  # utilise le canal courant
        }

        collection.insert_one(data)
        await interaction.response.send_message("✅ Chaîne ajoutée à la base de données MongoDB !", ephemeral=True)

# Fonction pour ajouter le COG
async def setup(bot):
    await bot.add_cog(YouTubeNotifier(bot))