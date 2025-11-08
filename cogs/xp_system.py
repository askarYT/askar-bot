import discord
from discord import app_commands, Role
from discord.ext import commands, tasks
from pymongo import MongoClient
from datetime import datetime, timedelta
import random
import logging
import os
import math

# Configuration des logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Définition des limites d'XP/LVL pour chaque type d'interaction
XP_LIMITS = {
    "message": {"min": 4, "max": 12},   # XP pour les messages
    "vocal": {"min": 5, "max": 11},     # XP pour les salons vocaux
    "reaction": {"min": 2, "max": 6},   # XP pour les réactions
    "levels": {"multiplicator": 0.22},  # Multiplicateur pour lvl-up
}

class XPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # --- Connexion à la base de données ---
        self.mongo_uri = os.getenv("MONGO_URI")
        if not self.mongo_uri:
            logging.error("Cog 'XPSystem': Erreur critique : URI MongoDB non configurée.")
            raise ValueError("La variable d'environnement MONGO_URI est obligatoire.")
        
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client["askar_bot"]
            self.xp_collection = self.db["xp_data"]
            self.level_roles_collection = self.db["level_roles"]
            self.ignored_channels_collection = self.db["ignored_channels"]
            self.command_levels_collection = self.db["command_levels"] # Nouvelle collection pour les permissions par niveau
            logging.info("Cog 'XPSystem': Connexion à MongoDB réussie.")
        except Exception as e:
            logging.error(f"Cog 'XPSystem': Erreur lors de la connexion à MongoDB : {e}")
            raise

        # Dictionnaires en mémoire pour la gestion des cooldowns et états
        self.vocal_timers = {} # {user_id: task}
        self.last_message_xp = {}
        self.reaction_tracking = {}

        # Collection pour les rôles par niveau
        # Démarre la tâche de resynchronisation des rôles toutes les 15 minutes
        self.sync_roles_task.start()

    def cog_unload(self):
        """Annule les tâches lorsque le cog est déchargé."""
        self.sync_roles_task.cancel()
        for timer in self.vocal_timers.values():
            timer.cancel()

    def get_user_data(self, user_id):
        """Récupère les données d'XP et de niveau d'un utilisateur depuis MongoDB."""
        try:
            user_data = self.xp_collection.find_one({"user_id": user_id})
            if not user_data:
                return {"user_id": user_id, "xp": 0, "level": 1}
            return user_data
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des données d'utilisateur : {e}")
            return {"user_id": user_id, "xp": 0, "level": 1}

    def update_user_data(self, user_id, xp_amount, source):
        """Mise à jour synchrone des données d'XP et retourne les niveaux."""
        try:
            user_data = self.get_user_data(user_id)
            old_level = user_data["level"]
            new_xp = user_data["xp"] + xp_amount
            new_level = self.calculate_level(new_xp)

            # Mise à jour des données d'XP et de niveau
            self.xp_collection.update_one(
                {"user_id": user_id},
                {"$set": {"xp": new_xp, "level": new_level}},
                upsert=True
            )
            
            logging.info(f"Ajout de {xp_amount} XP pour l'utilisateur {user_id} (source : {source}). Nouveau niveau : {new_level}.")
            return old_level, new_level
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour des données d'XP : {e}")
            return None, None

    async def handle_level_up(self, user_id, old_level, new_level):
        """Gère les actions asynchrones lors d'un gain de niveau."""
        if new_level <= old_level:
            return

        logging.info(f"L'utilisateur {user_id} a atteint le niveau {new_level}.")

        # Attribuer les rôles
        all_level_roles = self.level_roles_collection.find({"guild_id": {"$exists": True}})
        for level_role in all_level_roles:
            if old_level < level_role["level"] <= new_level:
                guild = self.bot.get_guild(level_role["guild_id"])
                if guild:
                    member = guild.get_member(int(user_id))
                    role = guild.get_role(level_role["role_id"])
                    if member and role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason=f"Atteint le niveau {level_role['level']}")
                            logging.info(f"Rôle '{role.name}' attribué à {member.display_name} pour avoir atteint le niveau {level_role['level']}.")
                        except discord.Forbidden:
                            logging.warning(f"Permission manquante pour attribuer le rôle '{role.name}' à {member.display_name}.")
                        except Exception as e:
                            logging.error(f"Erreur lors de l'attribution du rôle : {e}")

        # Envoyer un message privé (si activé)
        user = self.bot.get_user(int(user_id))
        if user:
            # La logique de notification peut être ajoutée ici.
            # ex: await user.send(f"Félicitations ! 🎉 Tu as atteint le niveau {new_level} !")
            pass

    def calculate_level(self, xp):
        """Calcule le niveau d'un utilisateur en fonction de son XP."""
        # Exemple ajusté : augmenter le taux en utilisant un exposant légèrement inférieur à 0.5
        level = math.floor(xp ** XP_LIMITS["levels"]["multiplicator"])  # Ajuster ici le diviseur et l'exposant
        return level

    def is_channel_ignored(self, channel_id):
        """Vérifie si un salon est ignoré pour les gains d'XP."""
        ignored_channel = self.ignored_channels_collection.find_one({"channel_id": channel_id})
        return ignored_channel is not None

    def has_command_permission(self, command_name, user):
        """Vérifie si l'utilisateur a la permission d'utiliser une commande."""
        try:
            # Exceptions pour certaines commandes accessibles à tous
            if command_name in ["xp"]:
                return True
            
            # Vérification par niveau
            command_level_req = self.command_levels_collection.find_one({"command": command_name})
            
            # S'il n'y a pas de restriction de niveau, la commande est autorisée par défaut.
            if not command_level_req:
                return True

            # Si une restriction existe, on vérifie le niveau de l'utilisateur
            user_data = self.get_user_data(str(user.id))
            user_level = user_data.get("level", 1)
            required_level = command_level_req.get("level", float('inf')) # Niveau infini si non défini
            return user_level >= required_level
        except Exception as e:
            logging.error(f"Erreur lors de la vérification des permissions pour la commande {command_name} : {e}")
            return False

    @commands.Cog.listener()
    async def on_message(self, message):
        """Ajoute de l'XP lorsqu'un utilisateur envoie un message(si le salon n'est pas ignoré)."""
        if message.author.bot or self.is_channel_ignored(message.channel.id):
            return
        
        user_id = str(message.author.id)
        now = datetime.utcnow()

        # Ajout d'un délai minimum entre les gains d'XP pour les messages
        if user_id in self.last_message_xp and now - self.last_message_xp[user_id] < timedelta(seconds=60):
            return
        
        self.last_message_xp[user_id] = now
        xp_gained = random.randint(XP_LIMITS["message"]["min"], XP_LIMITS["message"]["max"])
        old_level, new_level = self.update_user_data(user_id, xp_gained, source="Message")
        if old_level is not None and new_level > old_level:
            await self.handle_level_up(user_id, old_level, new_level)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Ajoute de l'XP lorsqu'un utilisateur réagit à un message (si le salon n'est pas ignoré)."""
        if user.bot or self.is_channel_ignored(reaction.message.channel.id):
            return
        
        message_id = str(reaction.message.id)
        user_id = str(user.id)

        # Empêcher de gagner de l'XP plusieurs fois pour la même réaction/message
        if message_id in self.reaction_tracking and user_id in self.reaction_tracking[message_id]:
            return
        
        if message_id not in self.reaction_tracking:
            self.reaction_tracking[message_id] = set()

        self.reaction_tracking[message_id].add(user_id)
        xp_gained = random.randint(XP_LIMITS["reaction"]["min"], XP_LIMITS["reaction"]["max"])
        old_level, new_level = self.update_user_data(user_id, xp_gained, source="Réaction")
        if old_level is not None and new_level > old_level:
            await self.handle_level_up(user_id, old_level, new_level)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Ajoute de l'XP lorsqu'un utilisateur est actif dans un salon vocal."""
        user_id = str(member.id)
        if member.bot:
            return

        # Si l'utilisateur rejoint un salon vocal
        if after.channel and not before.channel:
            if self.is_channel_ignored(after.channel.id):  # Vérifie si le salon est ignoré
                return
            if user_id not in self.vocal_timers:
                # Démarrer un timer pour cet utilisateur
                self.vocal_timers[user_id] = self.start_vocal_timer(member)

        # Si l'utilisateur quitte le salon vocal
        elif not after.channel and before.channel:
            if user_id in self.vocal_timers:
                # Annuler le timer de cet utilisateur
                self.vocal_timers[user_id].cancel()
                del self.vocal_timers[user_id]

    def start_vocal_timer(self, member):
        """Démarre un timer pour ajouter de l'XP toutes les minutes."""
        async def add_vocal_xp():
            while True:
                await asyncio.sleep(60)
                if not member.voice or not member.voice.channel:  # Vérifie si l'utilisateur est encore en vocal
                    break
                xp_gained = random.randint(XP_LIMITS["vocal"]["min"], XP_LIMITS["vocal"]["max"])
                old_level, new_level = self.update_user_data(str(member.id), xp_gained, source="Vocal")
                if old_level is not None and new_level > old_level:
                    await self.handle_level_up(str(member.id), old_level, new_level)

        import asyncio

        return self.bot.loop.create_task(add_vocal_xp())

    @app_commands.command(name="xp", description="Affiche l'XP et le niveau d'un utilisateur.")
    async def check_xp(self, interaction: discord.Interaction, user: discord.Member = None):
        """Commande slash pour vérifier l'XP et le niveau d'un utilisateur."""
        if not self.has_command_permission("xp", interaction.user):
            await interaction.response.send_message(
                "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        try:
            # La réponse est éphémère, pas besoin de defer si le traitement est rapide.
            await interaction.response.defer(ephemeral=True)

            target_user = user if user else interaction.user
            user_id = str(target_user.id)
            user_data = self.get_user_data(user_id)
            xp = user_data.get("xp", 0)
            level = user_data.get("level", 1)

            # Calcul de l'XP nécessaire pour passer au niveau suivant
            xp_next_level = math.ceil((level + 1) ** (1 / XP_LIMITS["levels"]["multiplicator"]))

            # Envoie la réponse finale
            await interaction.followup.send(
                f"**{target_user.display_name}** est au **niveau {level}** avec **{xp} XP**.\n"
                f"Il manque **{xp_next_level - xp} XP** pour le prochain niveau."
            )
        except discord.errors.NotFound:
            logging.error("L'interaction n'est plus valide ou a expiré.")
        except Exception as e:
            logging.error(f"Erreur lors du traitement de la commande /xp : {e}")

    @app_commands.command(name="xp-add", description="Ajoute de l'XP à un utilisateur.")
    @app_commands.describe(user="L'utilisateur à modifier.", xp_amount="Montant d'XP à ajouter.")
    async def add_xp(self, interaction: discord.Interaction, user: discord.Member, xp_amount: int):
        """Ajoute de l'XP à un utilisateur."""
        if not self.has_command_permission("xp-add", interaction.user):
            await interaction.response.send_message(
                "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return
        
        try:
            old_level, new_level = self.update_user_data(
                str(user.id), 
                xp_amount, 
                source=f"Manuel (par {interaction.user.display_name})"
            )
            if old_level is not None and new_level > old_level:
                await self.handle_level_up(str(user.id), old_level, new_level)

            await interaction.response.send_message(
                f"Ajout de {xp_amount} XP à {user.mention} (par {interaction.user.mention}).", ephemeral=True
            )
        except Exception as e:
            logging.error(f"Erreur lors de l'ajout d'XP : {e}")
            await interaction.response.send_message("Une erreur est survenue lors de l'ajout d'XP.", ephemeral=True)

    @app_commands.command(name="xp-remove", description="Retire de l'XP à un utilisateur.")
    @app_commands.describe(user="L'utilisateur à modifier.", xp_amount="Montant d'XP à retirer.")
    async def remove_xp(self, interaction: discord.Interaction, user: discord.Member, xp_amount: int):
        """Retire de l'XP à un utilisateur."""
        if not self.has_command_permission("xp-remove", interaction.user):
            await interaction.response.send_message(
                "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return
        
        try:
            old_level, new_level = self.update_user_data(
                str(user.id), 
                -xp_amount, 
                source=f"Manuel (par {interaction.user.display_name})"
            )
            if old_level is not None and new_level > old_level:
                await self.handle_level_up(str(user.id), old_level, new_level)

            await interaction.response.send_message(
                f"Retrait de {xp_amount} XP à {user.mention} (par {interaction.user.mention}).", ephemeral=True
            )
        except Exception as e:
            logging.error(f"Erreur lors du retrait d'XP : {e}")
            await interaction.response.send_message("Une erreur est survenue lors du retrait d'XP.", ephemeral=True)

    @app_commands.command(name="ignore-channel", description="Ajoute un salon (textuel ou vocal) à la liste des salons ignorés pour les gains d'XP.")
    @app_commands.describe(channel="Le salon (textuel ou vocal) à ignorer.")
    async def ignore_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):
        """Ajoute un salon (textuel ou vocal) à la liste des salons ignorés."""
        if not self.has_command_permission("ignore-channel", interaction.user):
            await interaction.response.send_message(
                "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        try:
            self.ignored_channels_collection.update_one(
                {"channel_id": channel.id},
                {"$set": {"channel_id": channel.id}},
                upsert=True
            )
            await interaction.response.send_message(f"Le salon {channel.mention} est maintenant ignoré pour les gains d'XP.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erreur lors de l'ajout du salon ignoré : {e}")
            await interaction.response.send_message("Une erreur est survenue lors de l'ajout du salon à la liste ignorée.", ephemeral=True)

    @app_commands.command(name="unignore-channel", description="Supprime un salon (textuel ou vocal) de la liste des salons ignorés pour les gains d'XP.")
    @app_commands.describe(channel="Le salon (textuel ou vocal) à ne plus ignorer.")
    async def unignore_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):
        """Supprime un salon (textuel ou vocal) de la liste des salons ignorés."""
        if not self.has_command_permission("unignore-channel", interaction.user):
            await interaction.response.send_message(
                "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
            )
            return

        try:
            self.ignored_channels_collection.delete_one({"channel_id": channel.id})
            await interaction.response.send_message(f"Le salon {channel.mention} n'est plus ignoré pour les gains d'XP.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erreur lors de la suppression du salon ignoré : {e}")
            await interaction.response.send_message("Une erreur est survenue lors de la suppression du salon de la liste ignorée.", ephemeral=True)

    @app_commands.command(name="set-command-level", description="Définit le niveau minimum requis pour utiliser une commande.")
    @app_commands.describe(command="La commande à configurer.", level="Le niveau minimum requis.")
    async def set_command_level(self, interaction: discord.Interaction, command: str, level: int):
        """Définit un niveau minimum requis pour une commande spécifique."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
            return
        
        if level <= 0:
            await interaction.response.send_message("Le niveau doit être supérieur à 0.", ephemeral=True)
            return

        try:
            self.command_levels_collection.update_one(
                {"command": command},
                {"$set": {"level": level}},
                upsert=True
            )
            await interaction.response.send_message(
                f"Le niveau **{level}** est maintenant requis pour utiliser la commande `/{command}`.",
                ephemeral=True
            )
        except Exception as e:
            logging.error(f"Erreur lors de la configuration du niveau pour la commande {command}: {e}")
            await interaction.response.send_message("Une erreur est survenue lors de la configuration du niveau.", ephemeral=True)

    @app_commands.command(name="remove-command-level", description="Supprime la restriction de niveau pour une commande.")
    @app_commands.describe(command="La commande dont la restriction doit être supprimée.")
    async def remove_command_level(self, interaction: discord.Interaction, command: str):
        """Supprime la restriction de niveau pour une commande."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
            return

        try:
            result = self.command_levels_collection.delete_one({"command": command})
            if result.deleted_count > 0:
                await interaction.response.send_message(f"La restriction de niveau pour la commande `/{command}` a été supprimée.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Aucune restriction de niveau n'était configurée pour la commande `/{command}`.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erreur lors de la suppression de la restriction de niveau pour {command}: {e}")
            await interaction.response.send_message("Une erreur est survenue.", ephemeral=True)

    @set_command_level.autocomplete("command")
    @remove_command_level.autocomplete("command")
    async def command_autocomplete(self, interaction: discord.Interaction, current: str):
        """Fournit une liste des commandes du bot pour l'auto-complétion."""
        commands = [
            cmd.name for cmd in self.bot.tree.get_commands()
            if cmd.name.startswith(current)  # Filtrer les commandes qui commencent par `current`
        ]
        return [app_commands.Choice(name=cmd, value=cmd) for cmd in commands]

    @app_commands.command(name="set-level-role", description="Assigne un rôle à donner à partir d'un niveau.")
    @app_commands.describe(level="Le niveau à atteindre", role="Le rôle à donner")
    async def set_level_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
            return
        try:
            self.level_roles_collection.update_one(
                {"level": level, "guild_id": interaction.guild.id},
                {"$set": {"level": level, "role_id": role.id, "guild_id": interaction.guild.id}},
                upsert=True
            )
            await interaction.response.send_message(
                f"Le rôle {role.mention} sera désormais donné à partir du niveau {level}.",
                ephemeral=True
            )
        except Exception as e:
            logging.error(f"Erreur lors de l'enregistrement du rôle pour le niveau {level} : {e}")
            await interaction.response.send_message("Erreur lors de la configuration du rôle pour ce niveau.", ephemeral=True)


    @tasks.loop(minutes=15)
    async def sync_roles_task(self):
        for guild in self.bot.guilds:
            level_roles = list(self.level_roles_collection.find({"guild_id": guild.id}))
            if not level_roles:
                continue

            for member in guild.members:
                if member.bot:
                    continue

                user_data = self.get_user_data(str(member.id))
                level = user_data.get("level", 1)

                for role_entry in level_roles:
                    role = guild.get_role(role_entry["role_id"])
                    if role and level >= role_entry["level"] and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="Resynchronisation automatique des rôles par niveau")
                            logging.info(f"Rôle '{role.name}' réattribué à {member.display_name} (niveau {level}) via resync.")
                        except discord.Forbidden:
                            logging.warning(f"Permission manquante pour réattribuer le rôle '{role.name}' à {member.display_name} via resync.")
                        except Exception as e:
                            logging.error(f"Erreur lors de la réattribution automatique du rôle : {e}")

    @sync_roles_task.before_loop
    async def before_sync_roles(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="resync-roles", description="Force la resynchronisation des rôles par niveau pour tous les membres.")
    async def resync_roles(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        level_roles = list(self.level_roles_collection.find({"guild_id": guild.id}))
        if not level_roles:
            await interaction.followup.send("Aucun rôle par niveau n'a été configuré pour ce serveur.")
            return

        count = 0
        for member in guild.members:
            if member.bot:
                continue
            user_data = self.get_user_data(str(member.id))
            level = user_data.get("level", 1)
            for role_entry in level_roles:
                role = guild.get_role(role_entry["role_id"])
                if role and level >= role_entry["level"] and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Synchronisation manuelle des rôles")
                        logging.info(f"Rôle '{role.name}' attribué à {member.display_name} via resync manuel.")
                        count += 1
                    except Exception as e:
                        logging.error(f"Erreur lors de la synchronisation manuelle des rôles : {e}")

        await interaction.followup.send(f"Synchronisation terminée. {count} rôles attribués.")


async def setup(bot):
    await bot.add_cog(XPSystem(bot))
