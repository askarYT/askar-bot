import discord
from discord.ext import commands, tasks
from discord import app_commands
from pymongo import MongoClient
import os
import logging
from twitchAPI.twitch import Twitch
from twitchAPI.helper import first

# Configuration des logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TwitchFollower(commands.Cog):
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
            self.follower_roles_collection = self.db["twitch_follower_roles"]
            self.user_links_collection = self.db["twitch_user_links"]
            logging.info("Cog 'TwitchFollower': Connexion à MongoDB réussie.")
        except Exception as e:
            logging.error(f"Cog 'TwitchFollower': Erreur lors de la connexion à MongoDB : {e}")
            raise

        # --- Initialisation de l'API Twitch ---
        self.twitch_client_id = os.getenv("TWITCH_CLIENT_ID")
        self.twitch_client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        if not self.twitch_client_id or not self.twitch_client_secret:
            logging.error("Erreur critique : Clés API Twitch manquantes.")
            raise ValueError("Les variables d'environnement TWITCH_CLIENT_ID et TWITCH_CLIENT_SECRET sont requises.")
        
        self.twitch = None
        self.bot.loop.create_task(self.initialize_twitch())

    async def initialize_twitch(self):
        """Initialise l'API Twitch de manière asynchrone."""
        try:
            self.twitch = await Twitch(self.twitch_client_id, self.twitch_client_secret, target_app_auth_scope=None)
            await self.twitch.authenticate_app([]) # Force l'authentification de l'application
            logging.info("Cog 'TwitchFollower': Client Twitch API initialisé avec succès.")
        except Exception as e:
            logging.error(f"Cog 'TwitchFollower': Échec de l'initialisation du client Twitch API : {e}")

    # --- Commandes d'administration ---

    @app_commands.command(name="twitch-set-follower-role", description="Définit le rôle à donner aux followers d'une chaîne.")
    @app_commands.describe(twitch_username="Le nom de la chaîne Twitch", role="Le rôle à assigner aux followers")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_follower_role(self, interaction: discord.Interaction, twitch_username: str, role: discord.Role):
        twitch_username_lower = twitch_username.lower()

        self.follower_roles_collection.update_one(
            {"guild_id": interaction.guild_id, "twitch_username": twitch_username_lower},
            {"$set": {
                "role_id": role.id
            }},
            upsert=True
        )

        await interaction.response.send_message(f"✅ Le rôle {role.mention} sera désormais utilisé pour les followers de **{twitch_username}**.", ephemeral=True)

    # --- Commandes utilisateur ---

    @app_commands.command(name="twitch-link", description="Lie ton compte Discord à un pseudo Twitch.")
    @app_commands.describe(twitch_username="Ton nom d'utilisateur sur Twitch")
    async def link_twitch_account(self, interaction: discord.Interaction, twitch_username: str):
        """Enregistre l'association entre un utilisateur Discord et un pseudo Twitch."""
        self.user_links_collection.update_one(
            {"discord_id": interaction.user.id},
            {"$set": {"twitch_username": twitch_username.lower()}},
            upsert=True
        )
        await interaction.response.send_message(f"✅ Ton compte Discord est maintenant lié au pseudo Twitch **{twitch_username}**.", ephemeral=True)

    @app_commands.command(name="twitch-verify-follow", description="Vérifie ton statut de follower et obtiens le rôle.")
    @app_commands.describe(twitch_username="La chaîne pour laquelle tu veux vérifier ton follow.")
    async def verify_follow(self, interaction: discord.Interaction, twitch_username: str):
        """Vérifie si un utilisateur suit une chaîne et lui attribue le rôle."""
        await interaction.response.defer(ephemeral=True)

        # 1. Récupérer le pseudo Twitch lié à l'utilisateur Discord
        user_link = self.user_links_collection.find_one({"discord_id": interaction.user.id})
        if not user_link:
            await interaction.followup.send("❌ Tu dois d'abord lier ton compte Twitch avec la commande `/twitch-link <ton_pseudo_twitch>`.")
            return

        linked_twitch_username = user_link['twitch_username']

        # 2. Récupérer le rôle configuré pour la chaîne cible
        role_config = self.follower_roles_collection.find_one({"guild_id": interaction.guild_id, "twitch_username": twitch_username.lower()})
        if not role_config:
            await interaction.followup.send(f"❌ Aucun rôle de follower n'est configuré pour la chaîne **{twitch_username}** sur ce serveur.")
            return

        role_to_assign = interaction.guild.get_role(role_config['role_id'])
        if not role_to_assign:
            await interaction.followup.send("❌ Le rôle configuré pour cette chaîne est introuvable. Contacte un administrateur.")
            return

        try:
            # 3. Utiliser l'API Twitch pour obtenir les IDs des utilisateurs
            users = await self.twitch.get_users(logins=[linked_twitch_username, twitch_username.lower()])
            user_id = None
            streamer_id = None
            async for user in users:
                if user.login == linked_twitch_username:
                    user_id = user.id
                if user.login == twitch_username.lower():
                    streamer_id = user.id

            if not user_id or not streamer_id:
                await interaction.followup.send("❌ Un des pseudos Twitch (le tien ou celui du streamer) est invalide.")
                return

            # 4. Vérifier si l'utilisateur suit la chaîne.
            # On récupère la liste des chaînes suivies par l'utilisateur
            # et on vérifie si la chaîne du streamer est dedans.
            # Cette méthode ne requiert qu'un token d'application.
            is_following = False
            try:
                async for follow in self.twitch.get_users_follows(from_id=user_id):
                    if follow.to_id == streamer_id:
                        is_following = True
                        break
            except Exception as e:
                logging.error(f"Erreur lors de la récupération des follows pour {linked_twitch_username}: {e}")

            member = interaction.user
            if is_following:
                # L'utilisateur suit la chaîne
                if role_to_assign not in member.roles:
                    await member.add_roles(role_to_assign, reason=f"Vérification de follow sur la chaîne Twitch {twitch_username}")
                    await interaction.followup.send(f"✅ Tu suis bien **{twitch_username}** ! Le rôle {role_to_assign.mention} t'a été attribué.")
                else:
                    await interaction.followup.send(f"✅ Tu suis bien **{twitch_username}** et tu as déjà le rôle {role_to_assign.mention}.")
            else:
                # L'utilisateur ne suit pas la chaîne
                if role_to_assign in member.roles:
                    await member.remove_roles(role_to_assign, reason=f"Ne suit plus la chaîne Twitch {twitch_username}")
                    await interaction.followup.send(f"ℹ️ Tu ne suis plus **{twitch_username}**. Le rôle {role_to_assign.mention} t'a été retiré.")
                else:
                    await interaction.followup.send(f"ℹ️ Tu ne suis pas la chaîne **{twitch_username}**. Tu n'as pas reçu le rôle.")

        except Exception as e:
            logging.error(f"Erreur lors de la vérification du follow Twitch : {e}")
            await interaction.followup.send("❌ Une erreur est survenue en communiquant avec l'API Twitch. Réessaye plus tard.")

    # --- Autocomplétion ---

    @set_follower_role.autocomplete('twitch_username')
    @verify_follow.autocomplete('twitch_username')
    async def twitch_username_autocomplete(self, interaction: discord.Interaction, current: str):
        """Propose les noms des streamers configurés pour le rôle de follower."""
        # On cherche dans la collection des rôles de followers
        alerts = self.follower_roles_collection.find({
            "guild_id": interaction.guild_id,
            "twitch_username": {"$regex": f"^{current}", "$options": "i"}
        }).limit(25)
        return [
            app_commands.Choice(name=alert['twitch_username'], value=alert['twitch_username'])
            for alert in alerts
        ]

async def setup(bot):
    await bot.add_cog(TwitchFollower(bot))
