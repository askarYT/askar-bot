import discord
from discord.ext import commands, tasks
from discord import ui
from discord import app_commands
from pymongo import MongoClient
import os
import logging
from datetime import datetime, timezone
import googleapiclient.discovery
import googleapiclient.errors

class YouTubeMessageModal(ui.Modal):
    def __init__(self, parent_cog, channel_name: str, current_video_message: str, current_short_message: str):
        super().__init__(title=f"Messages pour {channel_name}")
        self.parent_cog = parent_cog
        self.channel_name = channel_name

        self.video_message_input = ui.TextInput(
            label="Message pour les Vidéos",
            style=discord.TextStyle.paragraph,
            placeholder="Utilisez {channel}, {mention} et {url}. Laissez vide pour le message par défaut.",
            default=current_video_message,
            required=False,
            max_length=500
        )
        self.add_item(self.video_message_input)

        self.short_message_input = ui.TextInput(
            label="Message pour les Shorts",
            style=discord.TextStyle.paragraph,
            placeholder="Utilisez {channel}, {mention} et {url}. Laissez vide pour le message par défaut.",
            default=current_short_message,
            required=False,
            max_length=500
        )
        self.add_item(self.short_message_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_video_message = self.video_message_input.value if self.video_message_input.value.strip() != "" else None
        new_short_message = self.short_message_input.value if self.short_message_input.value.strip() != "" else None

        update_fields = {}
        if new_video_message is not None:
            update_fields["custom_video_message"] = new_video_message
        else:
            update_fields["custom_video_message"] = None

        if new_short_message is not None:
            update_fields["custom_short_message"] = new_short_message
        else:
            update_fields["custom_short_message"] = None

        result = self.parent_cog.collection.update_one(
            {"youtube_channel_name": self.channel_name, "guild_id": interaction.guild_id},
            {"$set": update_fields}
        )

        if result.matched_count > 0:
            await interaction.response.send_message(f"✅ Messages personnalisés pour **{self.channel_name}** mis à jour.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Une erreur est survenue lors de la mise à jour pour **{self.channel_name}**.", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logging.error(f"Erreur dans YouTubeMessageModal: {error}")
        await interaction.response.send_message("Oups! Une erreur est survenue.", ephemeral=True)


class YouTubeNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # --- Connexion à la base de données ---
        self.mongo_uri = os.getenv("MONGO_URI")
        if not self.mongo_uri:
            logging.error("Erreur critique : URI MongoDB non configurée.")
            raise ValueError("La variable d'environnement MONGO_URI est obligatoire.")
        
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client["askar_bot"]
            self.collection = self.db["youtube_notifications"]
            logging.info("Cog 'YouTubeNotifier': Connexion à MongoDB réussie.")
        except Exception as e:
            logging.error(f"Cog 'YouTubeNotifier': Erreur lors de la connexion à MongoDB : {e}")
            raise

        # --- Initialisation de l'API YouTube ---
        self.youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        if not self.youtube_api_key:
            logging.error("Erreur critique : Clé API YouTube manquante.")
            raise ValueError("La variable d'environnement YOUTUBE_API_KEY est requise.")
        
        try:
            self.youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=self.youtube_api_key)
            logging.info("Cog 'YouTubeNotifier': Client YouTube API initialisé avec succès.")
        except Exception as e:
            logging.error(f"Cog 'YouTubeNotifier': Échec de l'initialisation du client YouTube API : {e}")
            raise

        # Dictionnaire pour suivre les vidéos déjà notifiées {channel_id: video_id}
        self.notified_videos = {}
        # Cache pour stocker l'ID de la playlist d'uploads d'une chaîne
        self.channel_uploads_ids = {}
        # Cache pour les handles YouTube -> channel ID
        self.handle_cache = {}

        self.check_videos.start()

    def cog_unload(self):
        self.check_videos.cancel()

    @tasks.loop(minutes=5)
    async def check_videos(self):
        all_alerts = list(self.collection.find({}))
        if not all_alerts:
            return

        for alert in all_alerts:
            channel_id = alert['youtube_channel_id']
            channel_name = alert['youtube_channel_name']
            
            try:
                # 1. Obtenir l'ID de la playlist "Uploads" de la chaîne (avec cache)
                if channel_id not in self.channel_uploads_ids:
                    channel_request = self.youtube.channels().list(part="contentDetails", id=channel_id)
                    channel_response = await self.bot.loop.run_in_executor(None, channel_request.execute)
                    self.channel_uploads_ids[channel_id] = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
                
                uploads_playlist_id = self.channel_uploads_ids[channel_id]

                # 2. Récupérer la dernière vidéo de cette playlist
                playlist_request = self.youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=uploads_playlist_id,
                    maxResults=1
                )
                playlist_response = await self.bot.loop.run_in_executor(None, playlist_request.execute)

                if not playlist_response.get("items"):
                    logging.warning(f"Aucune vidéo trouvée pour la chaîne YouTube {channel_name} ({channel_id}).")
                    continue

                latest_video = playlist_response["items"][0]
                video_id = latest_video["contentDetails"]["videoId"]
                video_title = latest_video["snippet"]["title"]
                video_url = f"https://www.youtube.com/watch?v={video_id}"

                # 3. Vérifier si c'est une nouvelle vidéo
                if self.notified_videos.get(channel_id) != video_id:
                    # Initialisation pour éviter de notifier au premier démarrage
                    if channel_id not in self.notified_videos:
                        self.notified_videos[channel_id] = video_id
                        logging.info(f"Initialisation de la dernière vidéo pour {channel_name} : {video_id}")
                        continue

                    logging.info(f"Nouvelle vidéo détectée pour {channel_name}: {video_title}")
                    self.notified_videos[channel_id] = video_id

                    # Déterminer si c'est un Short
                    is_short = "#short" in video_title.lower() or "#shorts" in latest_video["snippet"]["description"].lower()
                    video_type = "Short" if is_short else "Vidéo"
                    video_url = f"https://www.youtube.com/shorts/{video_id}" if is_short else f"https://www.youtube.com/watch?v={video_id}"

                    # 4. Envoyer la notification
                    discord_channel = self.bot.get_channel(alert['discord_channel_id'])
                    if not discord_channel:
                        continue

                    # Construire le message de notification
                    role_id = alert.get('short_role_id') if is_short else alert.get('video_role_id')
                    role = discord_channel.guild.get_role(role_id) if role_id else None
                    role_mention = role.mention if role else ""

                    custom_message_template = alert.get('custom_short_message') if is_short else alert.get('custom_video_message')

                    if is_short:
                        link_text = "Short"
                        default_message = f"**{channel_name}** a publié un nouveau [**{link_text}**]({video_url}) ! 🎬"
                    else:
                        link_text = "Vidéo"
                        default_message = f"**{channel_name}** a publié une nouvelle [**{link_text}**]({video_url}) ! 📹"

                    if custom_message_template:
                        # Le placeholder {mention} est remplacé par le texte formaté du rôle
                        content_message = custom_message_template.format(channel=channel_name, mention=role_mention, url=video_url)
                    else:
                        content_message = f"{default_message}\n-# {role_mention}" if role else default_message

                    try:
                        await discord_channel.send(content=content_message.strip())
                    except discord.Forbidden:
                        logging.warning(f"Permission manquante pour envoyer un message dans le salon {discord_channel.id}")

            except googleapiclient.errors.HttpError as e:
                logging.error(f"Erreur API YouTube pour {channel_name}: {e}")
            except Exception as e:
                logging.error(f"Erreur inattendue lors de la vérification de {channel_name}: {e}")

    @check_videos.before_loop
    async def before_check_videos(self):
        await self.bot.wait_until_ready()

    # --- Commandes d'administration ---

    @app_commands.command(name="youtube-add", description="Ajoute une notification pour une chaîne YouTube.")
    @app_commands.describe(channel_url="L'URL de la chaîne YouTube (ex: https://www.youtube.com/@MKBHD)", channel="Le salon où envoyer la notification", video_role="Rôle à mentionner pour les vidéos (optionnel)", short_role="Rôle à mentionner pour les shorts (optionnel)")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_youtube_alert(self, interaction: discord.Interaction, channel_url: str, channel: discord.TextChannel, video_role: discord.Role = None, short_role: discord.Role = None):
        await interaction.response.defer(ephemeral=True)
        try:
            # Extraire l'ID ou le nom custom de l'URL
            if "/channel/" in channel_url:
                channel_id = channel_url.split("/channel/")[1].split("/")[0]
                request = self.youtube.channels().list(part="snippet", id=channel_id)
            elif "/@" in channel_url:
                handle = channel_url.split("/@")[1].split("/")[0]
                # Le paramètre forUsername est déprécié. On doit utiliser la recherche.
                # On vérifie d'abord notre cache
                if handle in self.handle_cache:
                    request = self.youtube.channels().list(part="snippet", id=self.handle_cache[handle])
                else:
                    # On recherche la chaîne par son handle
                    search_request = self.youtube.search().list(part="snippet", q=f"@{handle}", type="channel", maxResults=1)
                    search_response = await self.bot.loop.run_in_executor(None, search_request.execute)
                    if not search_response.get("items"):
                        await interaction.followup.send(f"❌ Impossible de trouver une chaîne avec le handle `@{handle}`.")
                        return
                    channel_id = search_response["items"][0]["id"]["channelId"]
                    request = self.youtube.channels().list(part="snippet", id=channel_id)
            else:
                await interaction.followup.send("❌ URL de chaîne YouTube invalide.")
                return

            response = await self.bot.loop.run_in_executor(None, request.execute)
            if not response.get("items"):
                await interaction.followup.send("❌ Impossible de trouver cette chaîne YouTube via l'API.")
                return

            yt_channel_info = response["items"][0]
            yt_channel_id = yt_channel_info["id"]
            yt_channel_name = yt_channel_info["snippet"]["title"]

            # Mettre en cache le handle si on l'a trouvé via la recherche
            if "/@" in channel_url:
                self.handle_cache[handle] = yt_channel_id

            if self.collection.find_one({"youtube_channel_id": yt_channel_id, "guild_id": interaction.guild_id}):
                await interaction.followup.send(f"❌ Une alerte pour **{yt_channel_name}** existe déjà.")
                return

            new_alert = {
                "guild_id": interaction.guild_id,
                "youtube_channel_id": yt_channel_id,
                "youtube_channel_name": yt_channel_name,
                "discord_channel_id": channel.id,
                "video_role_id": video_role.id if video_role else None,
                "short_role_id": short_role.id if short_role else None,
                "custom_video_message": None,
                "custom_short_message": None
            }
            self.collection.insert_one(new_alert)
            await interaction.followup.send(f"✅ Alerte activée pour **{yt_channel_name}** dans {channel.mention}.")

        except Exception as e:
            logging.error(f"Erreur lors de l'ajout d'une alerte YouTube : {e}")
            await interaction.followup.send("❌ Une erreur est survenue. Vérifiez l'URL et réessayez.")

    @app_commands.command(name="youtube-edit", description="Modifie une alerte YouTube existante.")
    @app_commands.describe(channel_name="Le nom de la chaîne à modifier", channel="Le nouveau salon", video_role="Le nouveau rôle pour les vidéos", short_role="Le nouveau rôle pour les shorts")
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_youtube_alert(self, interaction: discord.Interaction, channel_name: str, channel: discord.TextChannel = None, video_role: discord.Role = None, short_role: discord.Role = None):
        if not any([channel, video_role, short_role]):
            await interaction.response.send_message("❌ Vous devez spécifier au moins un champ à modifier.", ephemeral=True)
            return

        update_data = {}
        if channel:
            update_data["discord_channel_id"] = channel.id
        if video_role:
            update_data["video_role_id"] = video_role.id
        if short_role:
            update_data["short_role_id"] = short_role.id

        result = self.collection.update_one(
            {"youtube_channel_name": channel_name, "guild_id": interaction.guild_id},
            {"$set": update_data}
        )

        if result.matched_count > 0:
            await interaction.response.send_message(f"✅ L'alerte pour **{channel_name}** a été mise à jour.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Aucune alerte trouvée pour **{channel_name}**.", ephemeral=True)

    @app_commands.command(name="youtube-set-message", description="Définit les messages personnalisés pour une chaîne.")
    @app_commands.describe(channel_name="Le nom de la chaîne YouTube à configurer")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_youtube_message(self, interaction: discord.Interaction, channel_name: str):
        alert = self.collection.find_one({"youtube_channel_name": channel_name, "guild_id": interaction.guild_id})

        if not alert:
            await interaction.response.send_message(f"❌ Aucune alerte trouvée pour **{channel_name}**.", ephemeral=True)
            return

        current_video_message = alert.get("custom_video_message", "")
        current_short_message = alert.get("custom_short_message", "")

        modal = YouTubeMessageModal(
            parent_cog=self,
            channel_name=channel_name,
            current_video_message=current_video_message,
            current_short_message=current_short_message
        )
        await interaction.response.send_modal(modal)
        
    @app_commands.command(name="youtube-remove", description="Supprime une notification YouTube.")
    @app_commands.describe(channel_name="Le nom de la chaîne YouTube à retirer")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_youtube_alert(self, interaction: discord.Interaction, channel_name: str):
        result = self.collection.delete_one({"youtube_channel_name": channel_name, "guild_id": interaction.guild_id})

        if result.deleted_count > 0:
            # Nettoyer les dictionnaires en mémoire
            # (Cette partie est plus complexe si plusieurs serveurs suivent la même chaîne, mais pour un seul serveur c'est ok)
            alerts_for_channel = list(self.collection.find({"youtube_channel_name": channel_name}))
            # Pour nettoyer la mémoire, il faudrait retrouver le channel_id à partir du nom
            # C'est plus simple de laisser la boucle de vérification gérer les erreurs ou de ne rien faire.
            # Le cache se videra au redémarrage du bot.
            if not alerts_for_channel:
                alert_doc = self.collection.find_one({"youtube_channel_name": channel_name})
                if alert_doc:
                    channel_id_to_remove = alert_doc['youtube_channel_id']
                    self.notified_videos.pop(channel_id_to_remove, None)
                    self.channel_uploads_ids.pop(channel_id_to_remove, None)
            await interaction.response.send_message(f"✅ L'alerte pour **{channel_name}** a été supprimée.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Aucune alerte trouvée pour **{channel_name}**.", ephemeral=True)

    @app_commands.command(name="youtube-list", description="Affiche toutes les alertes YouTube configurées.")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_youtube_alerts(self, interaction: discord.Interaction):
        alerts = list(self.collection.find({"guild_id": interaction.guild_id}))
        if not alerts:
            await interaction.response.send_message("Aucune alerte YouTube n'est configurée sur ce serveur.")
            return

        embed = discord.Embed(title="🚨 Alertes YouTube Actives", color=discord.Color.red())
        for alert in sorted(alerts, key=lambda x: x['youtube_channel_name']):
            channel = self.bot.get_channel(alert['discord_channel_id'])
            video_role = interaction.guild.get_role(alert.get('video_role_id')) if alert.get('video_role_id') else None
            short_role = interaction.guild.get_role(alert.get('short_role_id')) if alert.get('short_role_id') else None
            custom_video_msg = alert.get('custom_video_message')
            custom_short_msg = alert.get('custom_short_message')

            value_str = (
                f"**Salon :** {channel.mention if channel else 'Inconnu'}\n"
                f"**Rôle Vidéo :** {video_role.mention if video_role else 'Aucun'}\n"
                f"**Rôle Short :** {short_role.mention if short_role else 'Aucun'}\n"
                f"**Msg Vidéo :** {f'`{custom_video_msg}`' if custom_video_msg else 'Par défaut'}\n"
                f"**Msg Short :** {f'`{custom_short_msg}`' if custom_short_msg else 'Par défaut'}"
            )

            embed.add_field(
                name=f"👤 {alert['youtube_channel_name']}", 
                value=value_str,
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="youtube-test", description="Envoie une fausse notification pour tester la configuration.")
    @app_commands.describe(channel_name="Le nom de la chaîne YouTube pour le test")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_youtube_alert(self, interaction: discord.Interaction, channel_name: str):
        await interaction.response.defer(ephemeral=True)
        alert = self.collection.find_one({"youtube_channel_name": channel_name, "guild_id": interaction.guild_id})

        if not alert:
            await interaction.followup.send(f"❌ Aucune alerte configurée pour **{channel_name}**.")
            return

        channel = self.bot.get_channel(alert['discord_channel_id'])
        if not channel:
            await interaction.followup.send(f"❌ Le salon de notification configuré pour **{channel_name}** est introuvable.")
            return

        # Récupération des infos de la chaîne pour l'embed
        try:
            request = self.youtube.channels().list(part="snippet", id=alert['youtube_channel_id'])
            response = await self.bot.loop.run_in_executor(None, request.execute)
            channel_info = response["items"][0]
            profile_pic_url = channel_info["snippet"]["thumbnails"]["default"]["url"]
        except Exception as e:
            logging.warning(f"Impossible de récupérer les infos de la chaîne pour le test de {channel_name}: {e}")
            profile_pic_url = None

        # --- Construction des messages de test ---
        try:
            # --- Test pour une VIDÉO ---
            video_role = interaction.guild.get_role(alert.get('video_role_id')) if alert.get('video_role_id') else None
            video_role_mention = video_role.mention if video_role else ""
            custom_video_message_template = alert.get('custom_video_message')
            video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" # Lien de test

            if custom_video_message_template:
                video_content = custom_video_message_template.format(channel=channel_name, mention=video_role_mention, url=video_url)
            else:
                default_video_message = f"**{channel_name}** a publié une nouvelle [**Vidéo**]({video_url}) ! 📹 (Ceci est un test)"
                video_content = f"{default_video_message}\n-# {video_role_mention}" if video_role else default_video_message

            await channel.send(content=video_content.strip())

            # --- Test pour un SHORT ---
            short_role = interaction.guild.get_role(alert.get('short_role_id')) if alert.get('short_role_id') else None
            short_role_mention = short_role.mention if short_role else ""
            custom_short_message_template = alert.get('custom_short_message')
            short_url = "https://www.youtube.com/shorts/c_n_F5j6_eA" # Lien de test

            if custom_short_message_template:
                short_content = custom_short_message_template.format(channel=channel_name, mention=short_role_mention, url=short_url)
            else:
                default_short_message = f"**{channel_name}** a publié un nouveau [**Short**]({short_url}) ! 🎬 (Ceci est un test)"
                short_content = f"{default_short_message}\n-# {short_role_mention}" if short_role else default_short_message

            await channel.send(content=short_content.strip())

            await interaction.followup.send(f"✅ Notifications de test pour **{channel_name}** envoyées dans {channel.mention}.")

        except discord.Forbidden:
            await interaction.followup.send(f"❌ Je n'ai pas la permission d'envoyer de message dans le salon {channel.mention}.")

    @remove_youtube_alert.autocomplete('channel_name')
    @edit_youtube_alert.autocomplete('channel_name')
    @set_youtube_message.autocomplete('channel_name')
    @test_youtube_alert.autocomplete('channel_name')
    async def youtube_channel_autocomplete(self, interaction: discord.Interaction, current: str):
        alerts = self.collection.find({
            "guild_id": interaction.guild_id,
            "youtube_channel_name": {"$regex": f"^{current}", "$options": "i"}
        }).limit(25)
        return [
            app_commands.Choice(name=alert['youtube_channel_name'], value=alert['youtube_channel_name'])
            for alert in alerts
        ]

async def setup(bot):
    await bot.add_cog(YouTubeNotifier(bot))
