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
            latest_video_url_stored = doc.get("latest_video_url", "none")
            latest_short_url_stored = doc.get("latest_short_url", "none")  # ✅ nouvel attribut
            discord_channel_id = doc["notifying_discord_channel"]
            video_role_id = doc.get("video_role_id")
            short_role_id = doc.get("short_role_id")

            discord_channel = self.bot.get_channel(int(discord_channel_id))
            if not discord_channel:
                print(f"⚠️ Canal Discord introuvable : {discord_channel_id}")
                continue

            # Vérification des vidéos classiques
            print(f"🔍 Checking Videos for {channel_name}")
            video_html = requests.get(f"https://www.youtube.com/channel/{youtube_channel_id}/videos").text
            try:
                latest_video_id = re.search('(?<="videoId":").*?(?=")', video_html).group()
                latest_video_url = f"https://www.youtube.com/watch?v={latest_video_id}"
            except:
                latest_video_url = None

            if latest_video_url and latest_video_url != latest_video_url_stored:
                collection.update_one(
                    {"_id": youtube_channel_id},
                    {"$set": {"latest_video_url": latest_video_url}}
                )
                role_mention = f"<@&{video_role_id}>" if video_role_id else "@everyone"
                msg = f"{role_mention} {channel_name} a publié une nouvelle **vidéo** ! 📹\n{latest_video_url}"
                await discord_channel.send(msg)

            # ✅ Vérification des Shorts
            print(f"🔍 Checking Shorts for {channel_name}")
            shorts_html = requests.get(f"https://www.youtube.com/channel/{youtube_channel_id}/shorts").text
            try:
                latest_short_id = re.search('(?<="videoId":").*?(?=")', shorts_html).group()
                latest_short_url = f"https://www.youtube.com/shorts/{latest_short_id}"
            except:
                latest_short_url = None

            if latest_short_url and latest_short_url != latest_short_url_stored:
                collection.update_one(
                    {"_id": youtube_channel_id},
                    {"$set": {"latest_short_url": latest_short_url}}
                )
                role_mention = f"<@&{short_role_id}>" if short_role_id else "@everyone"
                msg = f"{role_mention} {channel_name} a publié un nouveau **Short** ! 🎬\n{latest_short_url}"
                await discord_channel.send(msg)

    @app_commands.command(name="set_alert", description="Ajoute une chaîne YouTube à surveiller.")
    async def set_alert(self, interaction: discord.Interaction, channel_id: str, channel_name: str, notif_channel: discord.TextChannel):
        existing = collection.find_one({"_id": channel_id})

        if existing:
            await interaction.response.send_message("❌ Cette chaîne est déjà suivie.", ephemeral=True)
            return

        data = {
            "_id": channel_id,
            "channel_name": channel_name,
            "latest_video_url": "none",
            "latest_short_url": "none",
            "notifying_discord_channel": str(notif_channel.id),  # ✅ Utilisation du salon défini
            "video_role_id": None,
            "short_role_id": None,
            "twitch_role_id": None
        }

        collection.insert_one(data)
        await interaction.response.send_message(
            f"✅ Chaîne **{channel_name}** ajoutée à la base de données ! Les notifications seront envoyées dans {notif_channel.mention}.",
            ephemeral=True
        )

    @app_commands.command(name="set_alert_roles", description="Définit les rôles à mentionner pour une chaîne.")
    async def set_alert_roles(
        self,
        interaction: discord.Interaction,
        channel_name: str,
        video_role: discord.Role = None,
        short_role: discord.Role = None,
        twitch_role: discord.Role = None
    ):
        result = collection.find_one({"channel_name": channel_name})
        if not result:
            await interaction.response.send_message("❌ Chaîne non trouvée dans la base de données.", ephemeral=True)
            return

        update_data = {}
        if video_role:
            update_data["video_role_id"] = str(video_role.id)
        if short_role:
            update_data["short_role_id"] = str(short_role.id)
        if twitch_role:
            update_data["twitch_role_id"] = str(twitch_role.id)

        if update_data:
            collection.update_one({"_id": result["_id"]}, {"$set": update_data})
            await interaction.response.send_message("✅ Rôles mis à jour avec succès.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Aucun rôle fourni à mettre à jour.", ephemeral=True)

    @app_commands.command(name="remove_alert", description="Supprime une alerte YouTube par nom de chaîne.")
    @app_commands.describe(channel_name="Nom exact de la chaîne à retirer")
    async def remove_alert(self, interaction: discord.Interaction, channel_name: str):
        result = collection.find_one({"channel_name": channel_name})
        if not result:
            await interaction.response.send_message("❌ Aucune chaîne trouvée avec ce nom.", ephemeral=True)
            return

        collection.delete_one({"_id": result["_id"]})
        await interaction.response.send_message(f"✅ Chaîne **{channel_name}** supprimée de la base de données.", ephemeral=True)

    @remove_alert.autocomplete("channel_name")
    async def channel_name_autocomplete(self, interaction: discord.Interaction, current: str):
        results = collection.find({"channel_name": {"$regex": f".*{current}.*", "$options": "i"}}).limit(25)
        return [app_commands.Choice(name=doc["channel_name"], value=doc["channel_name"]) for doc in results]

# Fonction pour ajouter le COG
async def setup(bot):
    await bot.add_cog(YouTubeNotifier(bot))