import discord
from discord.ext import commands, tasks
from discord import app_commands
from pymongo import MongoClient
import os
import logging
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
        self.notified_streams = {}

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
                    content_message = f"Hey {role.mention if role else ''} !"

                    if custom_message:
                        content_message = custom_message.format(
                            streamer=stream_data.user_name,
                            game=stream_data.game_name or "Non spécifié"
                        )

                    if channel:
                        embed = discord.Embed(
                            title=f"🔴 {stream_data.user_name} est en live sur Twitch !",
                            description=f"**{stream_data.title}**",
                            url=f"https://twitch.tv/{stream_data.user_login}",
                            color=discord.Color.purple()
                        )
                        embed.add_field(name="Jeu", value=stream_data.game_name or "Non spécifié", inline=True)
                        embed.set_image(url=stream_data.get_thumbnail_url(width=440, height=248))
                        embed.set_thumbnail(url="https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png")
                        embed.set_footer(text=f"Rejoignez le live !")
                        
                        try:
                            sent_message = await channel.send(content=content_message, embed=embed)
                            # Stocker les informations pour la notification de fin
                            self.notified_streams[username] = {
                                'stream_id': stream_data.id,
                                'message': sent_message,
                                'start_time': stream_data.started_at
                            }
                        except discord.Forbidden:
                            logging.warning(f"Permission manquante pour envoyer un message dans le salon {channel.id}")
            else: # Le streamer n'est pas en live
                # Si le streamer était dans notre liste de notifiés, on le retire
                if username in self.notified_streams:
                    notification_data = self.notified_streams[username]
                    original_message = notification_data['message']
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

    @app_commands.command(name="twitch-set-message", description="Définit un message personnalisé pour une notification Twitch.")
    @app_commands.describe(twitch_username="Le nom d'utilisateur Twitch", message="Le message personnalisé. Utilisez {streamer} et {game}.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_twitch_message(self, interaction: discord.Interaction, twitch_username: str, message: str):
        twitch_username = twitch_username.lower()
        result = self.collection.update_one(
            {"twitch_username": twitch_username, "guild_id": interaction.guild_id},
            {"$set": {"custom_message": message}}
        )
        if result.matched_count > 0:
            await interaction.response.send_message(f"✅ Message personnalisé pour **{twitch_username}** défini.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Aucune alerte trouvée pour **{twitch_username}**.", ephemeral=True)

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
            embed.add_field(name=f"👤 {alert['twitch_username']}", value=f"**Salon :** {channel.mention if channel else 'Inconnu'}\n**Rôle :** {role.mention if role else 'Aucun'}", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

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

        embed = discord.Embed(
            title=f"🔴 {twitch_username.capitalize()} est en live sur Twitch !",
            description="**Ceci est une notification de test**",
            url=f"https://twitch.tv/{twitch_username}",
            color=discord.Color.purple()
        )
        embed.add_field(name="Jeu", value="Just Chatting", inline=True)
        embed.set_image(url=f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{twitch_username}-440x248.jpg")
        embed.set_thumbnail(url="https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png")
        embed.set_footer(text="Rejoignez le live !")

        try:
            await channel.send(embed=embed)
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