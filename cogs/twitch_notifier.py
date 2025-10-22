import discord
from discord.ext import commands, tasks
from discord import app_commands
from pymongo import MongoClient
import asyncio
import os
import logging
from twitchAPI.helper import first
from twitchAPI.twitch import Twitch
from datetime import datetime, timezone

# Configuration des logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TwitchNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # --- Connexion à la base de données ---
        self.mongo_uri = os.getenv("MONGO_URI")
        if not self.mongo_uri:
            logging.error("Erreur critique : URI MongoDB non configurée.")
            raise ValueError("La variable d'environnement MONGO_URI est obligatoire.")
        
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client["askar_bot"] # Utilisation de la BDD principale
            self.collection = self.db["twitch_notifications"]
            logging.info("Cog 'TwitchNotifier': Connexion à MongoDB réussie.")
        except Exception as e:
            logging.error(f"Cog 'TwitchNotifier': Erreur lors de la connexion à MongoDB : {e}")
            raise

        # --- Initialisation de l'API Twitch ---
        self.twitch_client_id = os.getenv("TWITCH_CLIENT_ID")
        self.twitch_client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        if not self.twitch_client_id or not self.twitch_client_secret:
            logging.error("Erreur critique : Clés API Twitch manquantes.")
            raise ValueError("Les variables d'environnement TWITCH_CLIENT_ID et TWITCH_CLIENT_SECRET sont requises.")
        
        self.twitch = None # Sera initialisé de manière asynchrone

        # Dictionnaire pour suivre les sessions de stream déjà notifiées {user_login: {stream_id, message, start_time}}
        self.notified_streams = {} # {user_login: {'stream_id', 'message', 'start_time', 'image_update_task'}}

        # Démarrage de la tâche en arrière-plan
        self.bot.loop.create_task(self.initialize_twitch_and_start_loop())

    async def initialize_twitch_and_start_loop(self):
        """Initialise l'API Twitch de manière asynchrone et démarre la boucle."""
        try:
            self.twitch = await Twitch(self.twitch_client_id, self.twitch_client_secret)
            logging.info("Cog 'TwitchNotifier': Client Twitch API initialisé avec succès.")
            self.check_streams.start()
        except Exception as e:
            logging.error(f"Cog 'TwitchNotifier': Échec de l'initialisation du client Twitch API : {e}")

    def cog_unload(self):
        """Arrête la tâche lorsque le cog est déchargé."""
        self.check_streams.cancel()

    @tasks.loop(minutes=1)
    async def check_streams(self):
        """Vérifie périodiquement si les streamers enregistrés sont en live."""
        all_alerts = list(self.collection.find({}))
        if not all_alerts:
            return

        streamer_logins = [alert['twitch_username'] for alert in all_alerts]
        
        try:
            # Appel API pour récupérer les informations de tous les streams en une seule fois
            live_streams = {stream.user_login.lower(): stream async for stream in self.twitch.get_streams(user_login=streamer_logins)}
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des streams Twitch : {e}")
            return

        # Pour récupérer les photos de profil, on doit faire un appel séparé
        try:
            # Récupère les objets User de Twitch pour les streamers en live
            users_info = {user.login.lower(): user async for user in self.twitch.get_users(logins=[s.user_login for s in live_streams.values()])}
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des informations des utilisateurs Twitch : {e}")
            users_info = {}

        for alert in all_alerts:
            username = alert['twitch_username']
            stream_data = live_streams.get(username.lower())

            if stream_data: # Le streamer est en live
                # Vérifie si on a déjà notifié pour cette session de stream
                if username not in self.notified_streams or self.notified_streams[username]['stream_id'] != stream_data.id:
                    logging.info(f"{username} est en live ! Envoi de la notification.")
                    
                    # Préparation et envoi de la notification
                    channel = self.bot.get_channel(alert['discord_channel_id'])
                    role = channel.guild.get_role(alert['role_id']) if alert.get('role_id') else None
                    
                    custom_message = alert.get('custom_message')
                    role_mention = role.mention if role else ""

                    if custom_message is not None: # Si un message perso est défini (même vide)
                        content_message = custom_message.format(
                            streamer=stream_data.user_name,
                            game=stream_data.game_name or "Non spécifié",
                            mention=role_mention
                        )
                    else:
                        # Message par défaut
                        game_name = stream_data.game_name or "Non spécifié"
                        content_message = f"🟣 **{stream_data.user_name}**: *Stream On* sur **\"{game_name}\"** !"
                        if role:
                            content_message += f"\n-# Hey {role_mention} !"

                    if channel:
                        embed = discord.Embed(
                            title=f"🔴 {stream_data.user_name} est en live sur Twitch !",
                            description=f"**{stream_data.title}**",
                            url=f"https://twitch.tv/{stream_data.user_login}",
                            color=discord.Color.purple()
                        )
                        # Utilise la miniature du stream comme image principale
                        embed.add_field(name="Jeu", value=stream_data.game_name or "Non spécifié", inline=True)
                        thumbnail_url = stream_data.thumbnail_url.replace('{width}', '440').replace('{height}', '248')
                        embed.set_image(url=f"{thumbnail_url}?_={int(datetime.now().timestamp())}")
                        
                        # Utilise la photo de profil du streamer comme thumbnail
                        streamer_info = users_info.get(username.lower())
                        if streamer_info and streamer_info.profile_image_url:
                            embed.set_thumbnail(url=streamer_info.profile_image_url)

                        embed.set_footer(text=f"Rejoignez le live !")
                        try:
                            sent_message = await channel.send(content=content_message, embed=embed)
                            # Stocker les informations pour la notification de fin
                            self.notified_streams[username] = {
                                'stream_id': stream_data.id,
                                'message': sent_message,
                                'start_time': stream_data.started_at,
                                'image_update_task': None # Initialise la tâche de mise à jour d'image
                            }
                            # Planifier la mise à jour de l'image après un court délai
                            self.notified_streams[username]['image_update_task'] = self.bot.loop.create_task(
                                self.schedule_image_update(username, stream_data.id, sent_message)
                            )
                        except discord.Forbidden:
                            logging.warning(f"Permission manquante pour envoyer un message dans le salon {channel.id}")
            else: # Le streamer n'est pas en live
                # Si le streamer était dans notre liste de notifiés, on le retire
                if username in self.notified_streams:
                    notification_data = self.notified_streams[username]
                    original_message = notification_data['message']
                    # Annuler la tâche de mise à jour d'image si elle est toujours en attente
                    if notification_data['image_update_task'] and not notification_data['image_update_task'].done():
                        notification_data['image_update_task'].cancel()
                        logging.debug(f"Tâche de mise à jour d'image annulée pour {username}.")
                    start_time = notification_data['start_time']
                    duration = datetime.now(timezone.utc) - start_time

                    # Formatter la durée en H/M/S
                    hours, remainder = divmod(int(duration.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m {seconds}s"

                    offline_embed = discord.Embed(
                        description=f"Le live est terminé. Durée : **{duration_str}**",
                        color=discord.Color.dark_grey()
                    )
                    try:
                        await original_message.reply(embed=offline_embed)
                    except (discord.Forbidden, discord.NotFound):
                        logging.warning(f"Impossible de répondre au message de notification pour {username}.")
                    del self.notified_streams[username]

    @check_streams.before_loop
    async def before_check_streams(self):
        await self.bot.wait_until_ready()

    async def schedule_image_update(self, twitch_username: str, stream_id: str, message_to_edit: discord.Message):
        """
        Planifie une mise à jour de l'image de l'embed après un délai,
        pour s'assurer que la miniature du stream est bien générée.
        """
        try:
            await asyncio.sleep(120) # Attendre 2 minutes

            # Vérifier si le stream est toujours en cours et est le même
            # On utilise self.notified_streams pour s'assurer que le stream n'a pas été dénotifié ou remplacé
            if twitch_username not in self.notified_streams or self.notified_streams[twitch_username]['stream_id'] != stream_id:
                logging.debug(f"Mise à jour d'image annulée pour {twitch_username}: stream non trouvé ou ID différent.")
                return

            # Re-récupérer les informations du stream
            streams = await self.twitch.get_streams(user_login=[twitch_username])
            latest_stream_data = await first(streams)

            if latest_stream_data and latest_stream_data.id == stream_id:
                # Récupérer le message original pour édition
                fetched_message = await message_to_edit.channel.fetch_message(message_to_edit.id)
                if fetched_message.embeds:
                    current_embed = fetched_message.embeds[0]
                    new_thumbnail_url = latest_stream_data.thumbnail_url.replace('{width}', '440').replace('{height}', '248')
                    new_thumbnail_url_with_cache_buster = f"{new_thumbnail_url}?_={int(datetime.now().timestamp())}"

                    # Mettre à jour l'image si elle est différente de celle actuellement dans l'embed
                    # Cela garantit que l'édition ne se fait qu'une seule fois si l'image change
                    if not current_embed.image or current_embed.image.url != new_thumbnail_url_with_cache_buster:
                        current_embed.set_image(url=new_thumbnail_url_with_cache_buster)
                        await fetched_message.edit(embed=current_embed)
                        logging.info(f"Image de notification mise à jour pour {twitch_username} (stream ID: {stream_id}).")
                else:
                    logging.warning(f"Message {message_to_edit.id} pour {twitch_username} n'a pas d'embed à mettre à jour.")
        except discord.NotFound:
            logging.warning(f"Message de notification {message_to_edit.id} pour {twitch_username} introuvable lors de la mise à jour de l'image.")
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour de l'image pour {twitch_username} (stream ID: {stream_id}): {e}")
        finally:
            # Nettoyer la référence de la tâche une fois qu'elle est terminée (ou annulée)
            if twitch_username in self.notified_streams and self.notified_streams[twitch_username]['stream_id'] == stream_id:
                self.notified_streams[twitch_username]['image_update_task'] = None

    # --- Commandes d'administration ---

    @app_commands.command(name="twitch-add", description="Ajoute une notification de live Twitch.")
    @app_commands.describe(twitch_username="Le nom d'utilisateur Twitch (ex: pokimane)", channel="Le salon où envoyer la notification", role="Le rôle à mentionner (optionnel)")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_twitch_alert(self, interaction: discord.Interaction, twitch_username: str, channel: discord.TextChannel, role: discord.Role = None):
        twitch_username = twitch_username.lower()
        if self.collection.find_one({"twitch_username": twitch_username, "guild_id": interaction.guild_id}):
            await interaction.response.send_message(f"❌ Une alerte pour **{twitch_username}** existe déjà sur ce serveur.", ephemeral=True)
            return

        new_alert = {
            "guild_id": interaction.guild_id,
            "twitch_username": twitch_username,
            "discord_channel_id": channel.id,
            "role_id": role.id if role else None,
            "custom_message": None # Champ pour le message personnalisé
        }
        self.collection.insert_one(new_alert)
        await interaction.response.send_message(f"✅ Alerte activée pour **{twitch_username}** dans le salon {channel.mention}.", ephemeral=True)

    @app_commands.command(name="twitch-remove", description="Supprime une notification de live Twitch.")
    @app_commands.describe(twitch_username="Le nom d'utilisateur Twitch à retirer")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_twitch_alert(self, interaction: discord.Interaction, twitch_username: str):
        twitch_username = twitch_username.lower()
        result = self.collection.delete_one({"twitch_username": twitch_username, "guild_id": interaction.guild_id})

        if result.deleted_count > 0:
            # Retire aussi de la liste des notifiés en mémoire si présent
            if twitch_username in self.notified_streams:
                del self.notified_streams[twitch_username]
            await interaction.response.send_message(f"✅ L'alerte pour **{twitch_username}** a été supprimée.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Aucune alerte trouvée pour **{twitch_username}** sur ce serveur.", ephemeral=True)

    @app_commands.command(name="twitch-edit", description="Modifie une alerte Twitch existante.")
    @app_commands.describe(twitch_username="Le nom d'utilisateur Twitch à modifier", channel="Le nouveau salon de notification", role="Le nouveau rôle à mentionner")
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_twitch_alert(self, interaction: discord.Interaction, twitch_username: str, channel: discord.TextChannel = None, role: discord.Role = None):
        twitch_username = twitch_username.lower()
        if not channel and not role:
            await interaction.response.send_message("❌ Vous devez spécifier au moins un salon ou un rôle à modifier.", ephemeral=True)
            return

        update_data = {}
        if channel:
            update_data["discord_channel_id"] = channel.id
        if role:
            update_data["role_id"] = role.id

        result = self.collection.update_one(
            {"twitch_username": twitch_username, "guild_id": interaction.guild_id},
            {"$set": update_data}
        )

        if result.matched_count > 0:
            await interaction.response.send_message(f"✅ L'alerte pour **{twitch_username}** a été mise à jour.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Aucune alerte trouvée pour **{twitch_username}** sur ce serveur.", ephemeral=True)

    @app_commands.command(name="twitch-set-message", description="Définit un message personnalisé via une modale.")
    @app_commands.describe(twitch_username="Le nom d'utilisateur Twitch à configurer")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_twitch_message(self, interaction: discord.Interaction, twitch_username: str):
        twitch_username_lower = twitch_username.lower()
        alert = self.collection.find_one({"twitch_username": twitch_username_lower, "guild_id": interaction.guild_id})

        if not alert:
            await interaction.response.send_message(f"❌ Aucune alerte trouvée pour **{twitch_username}**.", ephemeral=True)
            return

        class MessageModal(discord.ui.Modal, title=f"Message pour {twitch_username}"):
            def __init__(self, parent_cog, twitch_user, current_message):
                super().__init__()
                self.parent_cog = parent_cog
                self.twitch_user = twitch_user
                self.message_input = discord.ui.TextInput(
                    label="Message personnalisé",
                    style=discord.TextStyle.paragraph,
                    placeholder="Utilisez {streamer}, {game}, {mention}. Laissez vide pour réinitialiser.",
                    default=current_message,
                    required=False,
                    max_length=500
                )
                self.add_item(self.message_input)

            async def on_submit(self, interaction: discord.Interaction):
                new_message = self.message_input.value
                message_to_set = new_message if new_message.strip() != "" else None

                self.parent_cog.collection.update_one(
                    {"twitch_username": self.twitch_user, "guild_id": interaction.guild_id},
                    {"$set": {"custom_message": message_to_set}}
                )
                if message_to_set:
                    await interaction.response.send_message(f"✅ Message personnalisé pour **{self.twitch_user}** mis à jour.", ephemeral=True)
                else:
                    await interaction.response.send_message(f"✅ Message personnalisé pour **{self.twitch_user}** réinitialisé.", ephemeral=True)

        current_message = alert.get("custom_message", "")
        await interaction.response.send_modal(MessageModal(self, twitch_username_lower, current_message))

    @app_commands.command(name="twitch-list", description="Affiche toutes les alertes Twitch configurées sur le serveur.")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_twitch_alerts(self, interaction: discord.Interaction):
        alerts = list(self.collection.find({"guild_id": interaction.guild_id}))
        if not alerts:
            await interaction.response.send_message("Aucune alerte Twitch n'est configurée sur ce serveur.")
            return

        embed = discord.Embed(title="🚨 Alertes Twitch Actives", color=discord.Color.purple())
        for alert in sorted(alerts, key=lambda x: x['twitch_username']):
            channel = self.bot.get_channel(alert['discord_channel_id'])
            role = interaction.guild.get_role(alert['role_id']) if alert.get('role_id') else None
            custom_msg = alert.get('custom_message')
            msg_status = f"`{custom_msg}`" if custom_msg else "Par défaut"

            embed.add_field(
                name=f"👤 {alert['twitch_username']}", 
                value=f"**Salon :** {channel.mention if channel else 'Inconnu'}\n"
                      f"**Rôle :** {role.mention if role else 'Aucun'}\n"
                      f"**Message :** {msg_status}", 
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="twitch-test", description="Envoie une fausse notification de live pour tester la configuration.")
    @app_commands.describe(twitch_username="Le nom d'utilisateur Twitch pour le test")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_twitch_alert(self, interaction: discord.Interaction, twitch_username: str):
        twitch_username = twitch_username.lower()
        alert = self.collection.find_one({"twitch_username": twitch_username, "guild_id": interaction.guild_id})

        if not alert:
            await interaction.response.send_message(f"❌ Aucune alerte configurée pour **{twitch_username}**.", ephemeral=True)
            return

        channel = self.bot.get_channel(alert['discord_channel_id'])
        if not channel:
            await interaction.response.send_message(f"❌ Le salon de notification configuré pour **{twitch_username}** est introuvable.", ephemeral=True)
            return

        role = interaction.guild.get_role(alert['role_id']) if alert.get('role_id') else None
        role_mention_text = role.name if role else "" # Pour le test, on ne mentionne pas, on affiche le nom

        # Récupération de la photo de profil pour le test
        profile_image_url = None
        try:
            async for user in self.twitch.get_users(logins=[twitch_username]):
                profile_image_url = user.profile_image_url
                break
        except Exception as e:
            logging.warning(f"Impossible de récupérer la photo de profil pour le test de {twitch_username}: {e}")


        # --- Logique de message identique à la notification réelle ---
        custom_message = alert.get('custom_message')

        if custom_message is not None:
            content_message = custom_message.format(
                streamer=twitch_username,
                game="Jeu de test",
                mention=role_mention_text
            )
        else:
            game_name = "Jeu de test"
            content_message = f"🟣 **{twitch_username}**: *Stream On* sur **\"{game_name}\"** !"
            if role:
                content_message += f"\n-# Hey {role.name} !" # On ne mentionne pas dans le test, on affiche le nom

        embed = discord.Embed(
            title=f"🔴 {twitch_username} est en live sur Twitch !",
            description="**Ceci est une notification de test**",
            url=f"https://twitch.tv/{twitch_username}",
            color=discord.Color.purple()
        )
        embed.add_field(name="Jeu", value="Jeu de test", inline=True)
        embed.set_image(url=f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{twitch_username}-440x248.jpg?_={int(datetime.now().timestamp())}")
        if profile_image_url:
            embed.set_thumbnail(url=profile_image_url)
        embed.set_footer(text="Rejoignez le live !")

        try:
            # Envoie le contenu et l'embed, comme pour une vraie notification
            await channel.send(content=content_message, embed=embed)
            await interaction.response.send_message(
                f"✅ Notification de test pour **{twitch_username}** envoyée dans {channel.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Je n'ai pas la permission d'envoyer de message dans le salon {channel.mention}.",
                ephemeral=True
            )

    @remove_twitch_alert.autocomplete('twitch_username')
    @test_twitch_alert.autocomplete('twitch_username')
    @edit_twitch_alert.autocomplete('twitch_username')
    @set_twitch_message.autocomplete('twitch_username')
    async def twitch_username_autocomplete(self, interaction: discord.Interaction, current: str):
        """Propose les noms des streamers déjà configurés."""
        alerts = self.collection.find({
            "guild_id": interaction.guild_id,
            "twitch_username": {"$regex": f"^{current}", "$options": "i"}
        }).limit(25)
        return [
            app_commands.Choice(name=alert['twitch_username'], value=alert['twitch_username'])
            for alert in alerts
        ]

async def setup(bot):
    await bot.add_cog(TwitchNotifier(bot))