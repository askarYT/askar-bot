import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import os
import logging
from datetime import datetime

# Liste des événements configurables
LOG_EVENTS = [
    "ban", "kick", "warn", "unban", "softban", "tempban",  # Sanctions
    "message_delete", "message_edit",                      # Messages
    "member_join", "member_leave", "member_update",        # Membres
    "channel_create", "channel_delete", "channel_update",  # Salons
    "role_create", "role_delete", "role_update"            # Rôles
]

class LogCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        self.mongo_uri = os.getenv("MONGO_URI")
        if not self.mongo_uri:
            raise ValueError("La variable d'environnement MONGO_URI est obligatoire.")
            
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client["askar_bot"]
            self.collection = self.db["log_configs"]
            logging.info("Cog 'LogCore': Connexion à MongoDB réussie.")
        except Exception as e:
            logging.error(f"Cog 'LogCore': Erreur MongoDB : {e}")
            raise

    async def send_log(self, guild: discord.Guild, event_type: str, embed: discord.Embed, file: discord.File = None):
        """
        Fonction centrale pour envoyer un log.
        Cherche si un salon est configuré pour cet event_type précis.
        """
        try:
            config = self.collection.find_one({"guild_id": guild.id})
            if not config:
                return

            # On cherche l'ID du salon pour cet événement précis
            channel_id = config.get("channels", {}).get(event_type)
            
            if channel_id:
                channel = guild.get_channel(channel_id)
                if channel:
                    # Ajout timestamp si absent
                    if not embed.timestamp:
                        embed.timestamp = datetime.utcnow()
                    
                    # Envoi
                    await channel.send(embed=embed, file=file)
                else:
                    logging.warning(f"LogCore: Salon {channel_id} introuvable sur {guild.name} pour l'event {event_type}.")
        except Exception as e:
            logging.error(f"LogCore: Erreur lors de l'envoi du log ({event_type}): {e}")

    @app_commands.command(name="set-log", description="Configure le salon de logs pour un événement précis.")
    @app_commands.describe(
        event="L'événement à logger (ex: ban, message_delete...)",
        channel="Le salon où envoyer ces logs"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log(self, interaction: discord.Interaction, event: str, channel: discord.TextChannel):
        """Lie un événement à un salon."""
        if event not in LOG_EVENTS:
            await interaction.response.send_message(f"❌ Événement inconnu. Choisissez parmi la liste proposée.", ephemeral=True)
            return

        try:
            # Mise à jour : on stocke { "channels": { "ban": 123, "kick": 123 } }
            self.collection.update_one(
                {"guild_id": interaction.guild_id},
                {"$set": {f"channels.{event}": channel.id}},
                upsert=True
            )
            
            await interaction.response.send_message(
                f"✅ Les logs pour **{event}** seront envoyés dans {channel.mention}.",
                ephemeral=True
            )
            
            # Log de test
            embed = discord.Embed(title="🔧 Configuration Logs", description=f"Log activé pour : **{event}**", color=discord.Color.green())
            await channel.send(embed=embed)

        except Exception as e:
            logging.error(f"Erreur configuration logs : {e}")
            await interaction.response.send_message("❌ Une erreur est survenue.", ephemeral=True)

    @set_log.autocomplete('event')
    async def event_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=evt, value=evt)
            for evt in LOG_EVENTS
            if current.lower() in evt.lower()
        ][:25]

async def setup(bot):
    await bot.add_cog(LogCore(bot))