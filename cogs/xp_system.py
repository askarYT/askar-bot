import discord
from discord import app_commands, Role
from discord.ext import commands, tasks
from pymongo import MongoClient
from datetime import datetime, timedelta
import random
import logging
import os
import math
import asyncio

# Définition des limites d'XP/LVL pour chaque type d'interaction
XP_LIMITS = {
    "message": {"min": 4, "max": 12},   # XP pour les messages
    "vocal": {"min": 5, "max": 11},     # XP pour les salons vocaux
    "reaction": {"min": 2, "max": 6},   # XP pour les réactions
    "levels": {"coefficient": 250},  # Coefficient pour la nouvelle formule de niveau
}

def has_xp_permission():
    """
    Décorateur de permission personnalisé pour les commandes d'application.
    Vérifie si l'utilisateur a le niveau requis pour utiliser la commande.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        # Récupère le cog XPSystem depuis l'instance du bot
        xp_cog = interaction.client.get_cog('XPSystem')
        command_name = interaction.command.name

        if not xp_cog:
            return False # Ne devrait jamais arriver si le bot est bien lancé

        is_allowed, required_level = xp_cog.has_command_permission(command_name, interaction.user)
        if not is_allowed:
            await interaction.response.send_message(
                f"❌ Tu n'as pas le niveau requis pour utiliser cette commande. (Niveau **{required_level}** requis)", ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

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

        # Variable pour s'assurer que la resynchronisation ne se fait qu'une fois
        self.initial_sync_done = False

        # Collection pour les rôles par niveau
        # Démarre la tâche de resynchronisation des rôles toutes les 15 minutes
        self.sync_roles_task.start()

        # Lance la resynchronisation des niveaux au démarrage
        self.bot.loop.create_task(self.resync_levels_on_startup())

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

    def update_user_data(self, user_id, user_name, xp_amount, source):
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

            logging.info(f"🔹 {xp_amount:+} XP pour {user_name} (ID: {user_id}) (source: {source}) | Total: {new_xp} XP | Niveau: {new_level}")
            return old_level, new_level
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour des données d'XP : {e}")
            return None, None

    async def handle_level_up(self, user_id, old_level, new_level):
        """Gère les actions asynchrones lors d'un gain de niveau."""
        if new_level <= old_level:
            return

        logging.info(f"LEVEL UP: Utilisateur {user_id} a atteint le niveau {new_level}.")

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
                            logging.info(f"Rôle '{role.name}' attribué à {member.name} (ID: {member.id}) pour avoir atteint le niveau {level_role['level']}.")
                        except discord.Forbidden:
                            logging.warning(f"Permission manquante pour attribuer le rôle '{role.name}' à {member.name} (ID: {member.id}).")
                        except Exception as e:
                            logging.error(f"Erreur lors de l'attribution du rôle : {e}")

        # Envoyer un message privé (si activé)
        # --- LOGGING XP LEVEL UP ---
        log_core = self.bot.get_cog("LogCore")
        if log_core:
            guild = self.bot.get_guild(int(list(self.level_roles_collection.find({"guild_id": {"$exists": True}}))[0]["guild_id"])) if self.bot.guilds else None
            # Note: Récupérer la guild est complexe ici car user_id est global. On essaie de logger si on trouve une guild commune ou via le contexte d'appel.
            # Pour simplifier, on ne log le level up que si on a le contexte (via on_message c'est possible, ici c'est plus dur).
            pass 

        user = self.bot.get_user(int(user_id))
        if user:
            # La logique de notification peut être ajoutée ici.
            # ex: await user.send(f"Félicitations ! 🎉 Tu as atteint le niveau {new_level} !")
            pass

    def calculate_level(self, xp):
        """Calcule le niveau d'un utilisateur en fonction de son XP."""
        if xp <= 0:
            return 1
        # Nouvelle formule quadratique : level = sqrt(xp / coefficient)
        # On retourne au minimum le niveau 1.
        level = math.floor(math.sqrt(xp / XP_LIMITS["levels"]["coefficient"]))
        return max(1, level)

    async def resync_levels_on_startup(self):
        """
        Au démarrage du bot, parcourt tous les utilisateurs et recalcule leur niveau
        en fonction de leur XP actuel pour assurer la cohérence avec la formule de niveau.
        """
        await self.bot.wait_until_ready()

        if self.initial_sync_done:
            return

        logging.info("Démarrage de la resynchronisation des niveaux de tous les utilisateurs...")
        
        all_users = self.xp_collection.find({})
        updated_count = 0

        for user_data in all_users:
            user_id = user_data["user_id"]
            current_xp = user_data.get("xp", 0)
            current_level = user_data.get("level", 1)
            
            correct_level = self.calculate_level(current_xp)

            if current_level != correct_level:
                self.xp_collection.update_one({"user_id": user_id}, {"$set": {"level": correct_level}})
                logging.info(f"Resync: Utilisateur {user_id} mis à jour du niveau {current_level} au niveau {correct_level}.")
                updated_count += 1
        
        logging.info(f"Resynchronisation des niveaux terminée. {updated_count} utilisateurs mis à jour.")
        self.initial_sync_done = True

    def is_channel_ignored(self, channel_id):
        """Vérifie si un salon est ignoré pour les gains d'XP."""
        ignored_channel = self.ignored_channels_collection.find_one({"channel_id": channel_id})
        return ignored_channel is not None

    def has_command_permission(self, command_name, user):
        """Vérifie si l'utilisateur a la permission d'utiliser une commande. Retourne (bool, required_level)."""
        try:
            # Exceptions pour certaines commandes accessibles à tous
            if command_name in ["xp"]:
                return True, 0

            # Vérification par niveau
            command_level_req = self.command_levels_collection.find_one({"command": command_name})

            # S'il n'y a pas de restriction de niveau, la commande est autorisée par défaut.
            if not command_level_req:
                return True, 0

            # Si une restriction existe, on vérifie le niveau de l'utilisateur
            user_data = self.get_user_data(str(user.id))
            user_level = user_data.get("level", 1)
            required_level = command_level_req.get("level", float('inf')) # Niveau infini si non défini
            is_allowed = user_level >= required_level
            return is_allowed, required_level
        except Exception as e:
            logging.error(f"Erreur lors de la vérification des permissions pour la commande {command_name} : {e}")
            return False, float('inf')


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
        old_level, new_level = self.update_user_data(user_id, message.author.name, xp_gained, source="Message")
        if old_level is not None and new_level > old_level:
            await self.handle_level_up(user_id, old_level, new_level)
            # Log Level Up
            log_core = self.bot.get_cog("LogCore")
            if log_core:
                embed = discord.Embed(title="🆙 Level Up !", description=f"{message.author.mention} est passé au niveau **{new_level}** !", color=discord.Color.gold())
                embed.add_field(name="Ancien Niveau", value=str(old_level), inline=True)
                embed.add_field(name="Nouveau Niveau", value=str(new_level), inline=True)
                await log_core.send_log(message.guild, "xp_gain", embed)

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
        old_level, new_level = self.update_user_data(user_id, user.name, xp_gained, source="Réaction")
        if old_level is not None and new_level > old_level:
            await self.handle_level_up(user_id, old_level, new_level)
            # Log Level Up (Réaction)
            log_core = self.bot.get_cog("LogCore")
            if log_core:
                embed = discord.Embed(title="🆙 Level Up !", description=f"{user.mention} est passé au niveau **{new_level}** !", color=discord.Color.gold())
                embed.add_field(name="Source", value="Réaction", inline=True)
                await log_core.send_log(reaction.message.guild, "xp_gain", embed)

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
                old_level, new_level = self.update_user_data(str(member.id), member.name, xp_gained, source="Vocal")
                if old_level is not None and new_level > old_level:
                    await self.handle_level_up(str(member.id), old_level, new_level)
                    await self.handle_level_up(str(member.id), member.name, old_level, new_level)
                    # Log Level Up (Vocal)
                    log_core = self.bot.get_cog("LogCore")
                    if log_core:
                        embed = discord.Embed(title="🆙 Level Up !", description=f"{member.mention} est passé au niveau **{new_level}** !", color=discord.Color.gold())
                        embed.add_field(name="Source", value="Vocal", inline=True)
                        await log_core.send_log(member.guild, "xp_gain", embed)


        return self.bot.loop.create_task(add_vocal_xp())

    @app_commands.command(name="xp", description="Affiche l'XP et le niveau d'un utilisateur.")
    async def check_xp(self, interaction: discord.Interaction, user: discord.Member = None):
        """Commande slash pour vérifier l'XP et le niveau d'un utilisateur."""
        try:
            # On diffère la réponse pour avoir le temps de calculer, en mode non-éphémère (visible par tous).
            await interaction.response.defer(ephemeral=False)

            target_user = user if user else interaction.user
            user_id = str(target_user.id)
            user_data = self.get_user_data(user_id)
            xp = user_data.get("xp", 0)
            level = user_data.get("level", 1)

            # Calcul de l'XP nécessaire pour passer au niveau suivant
            xp_next_level = XP_LIMITS["levels"]["coefficient"] * ((level + 1) ** 2)

            # Envoie la réponse finale
            await interaction.followup.send(
                f"`{target_user.name}` est au **niveau {level}** avec *{xp} XP*.\n"
                f"Il manque **{xp_next_level - xp} XP** pour le prochain niveau."
            )
        except discord.errors.NotFound:
            logging.error("L'interaction n'est plus valide ou a expiré.")
        except Exception as e:
            logging.error(f"Erreur lors du traitement de la commande /xp : {e}")

    @app_commands.command(name="xp-add", description="Ajoute de l'XP à un utilisateur.")
    @app_commands.describe(user="L'utilisateur à modifier.", xp_amount="Montant d'XP à ajouter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_xp(self, interaction: discord.Interaction, user: discord.Member, xp_amount: int):
        """Ajoute de l'XP à un utilisateur (Admin seulement)."""
        try:
            old_level, new_level = self.update_user_data(
                str(user.id), 
                user.name,
                xp_amount, 
                source=f"Manuel (par {interaction.user.name} | {interaction.user.id})"
            )
            if old_level is not None and new_level > old_level:
                await self.handle_level_up(str(user.id), old_level, new_level)
            
            # Log Admin Action
            log_core = self.bot.get_cog("LogCore")
            if log_core:
                embed = discord.Embed(title="📈 XP Ajouté (Admin)", description=f"{xp_amount} XP ajoutés à {user.mention}", color=discord.Color.green())
                embed.add_field(name="Admin", value=interaction.user.mention, inline=True)
                embed.add_field(name="Nouveau Niveau", value=str(new_level), inline=True)
                await log_core.send_log(interaction.guild, "xp_gain", embed)

            await interaction.response.send_message(
                f"Ajout de {xp_amount} XP à {user.mention} (par {interaction.user.mention}).", ephemeral=True
            )
        except Exception as e:
            logging.error(f"Erreur lors de l'ajout d'XP : {e}")
            await interaction.response.send_message("Une erreur est survenue lors de l'ajout d'XP.", ephemeral=True)

    @app_commands.command(name="xp-remove", description="Retire de l'XP à un utilisateur.")
    @app_commands.describe(user="L'utilisateur à modifier.", xp_amount="Montant d'XP à retirer.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_xp(self, interaction: discord.Interaction, user: discord.Member, xp_amount: int):
        """Retire de l'XP à un utilisateur (Admin seulement)."""
        try:
            old_level, new_level = self.update_user_data(
                str(user.id), 
                user.name,
                -xp_amount, 
                source=f"Manuel (par {interaction.user.name} | {interaction.user.id})"
            )
            if old_level is not None and new_level > old_level:
                await self.handle_level_up(str(user.id), old_level, new_level)

            # Log Admin Action
            log_core = self.bot.get_cog("LogCore")
            if log_core:
                embed = discord.Embed(title="📉 XP Retiré (Admin)", description=f"{xp_amount} XP retirés à {user.mention}", color=discord.Color.red())
                embed.add_field(name="Admin", value=interaction.user.mention, inline=True)
                embed.add_field(name="Nouveau Niveau", value=str(new_level), inline=True)
                await log_core.send_log(interaction.guild, "xp_gain", embed)

            await interaction.response.send_message(
                f"Retrait de {xp_amount} XP à {user.mention} (par {interaction.user.mention}).", ephemeral=True
            )
        except Exception as e:
            logging.error(f"Erreur lors du retrait d'XP : {e}")
            await interaction.response.send_message("Une erreur est survenue lors du retrait d'XP.", ephemeral=True)

    @app_commands.command(name="ignore-channel", description="Ajoute un salon (textuel ou vocal) à la liste des salons ignorés pour les gains d'XP.")
    @app_commands.describe(channel="Le salon (textuel ou vocal) à ignorer.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ignore_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):
        """Ajoute un salon (textuel ou vocal) à la liste des salons ignorés (Admin seulement)."""
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
    @app_commands.checks.has_permissions(administrator=True)
    async def unignore_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):
        """Supprime un salon (textuel ou vocal) de la liste des salons ignorés (Admin seulement)."""
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
    async def command_autocomplete(self, interaction: discord.Interaction, current: str):
        """Fournit une liste des commandes du bot pour l'auto-complétion."""
        commands = [
            cmd.name for cmd in self.bot.tree.get_commands()
            if cmd.name.startswith(current)  # Filtrer les commandes qui commencent par `current`
        ]
        return [app_commands.Choice(name=cmd, value=cmd) for cmd in commands[:25]]

    @remove_command_level.autocomplete("command")
    async def protected_command_autocomplete(self, interaction: discord.Interaction, current: str):
        """Propose uniquement les commandes qui ont une restriction de niveau."""
        protected_commands = self.command_levels_collection.find({
            "command": {"$regex": f"^{current}", "$options": "i"}
        }).limit(25)
        return [
            app_commands.Choice(name=doc['command'], value=doc['command'])
            for doc in protected_commands
        ]

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
                            logging.info(f"Rôle '{role.name}' réattribué à {member.name} (ID: {member.id}) (niveau {level}) via resync.")
                        except discord.Forbidden:
                            logging.warning(f"Permission manquante pour réattribuer le rôle '{role.name}' à {member.name} (ID: {member.id}) via resync.")
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
                        logging.info(f"Rôle '{role.name}' attribué à {member.name} (ID: {member.id}) via resync manuel.")
                        count += 1
                    except Exception as e:
                        logging.error(f"Erreur lors de la synchronisation manuelle des rôles : {e}")

        await interaction.followup.send(f"Synchronisation terminée. {count} rôles attribués.")


async def setup(bot):
    await bot.add_cog(XPSystem(bot))