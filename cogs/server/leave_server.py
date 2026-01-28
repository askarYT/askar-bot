import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import os
import logging

class LeaveServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Connexion à MongoDB
        self.mongo_uri = os.getenv("MONGO_URI")
        if not self.mongo_uri:
            logging.error("Erreur : URI MongoDB non configurée.")
            raise ValueError("La variable d'environnement MONGO_URI est obligatoire.")
            
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client["askar_bot"]
            self.collection = self.db["leave_server_config"]
            logging.info("Cog 'LeaveServer': Connexion à MongoDB réussie.")
        except Exception as e:
            logging.error(f"Cog 'LeaveServer': Erreur lors de la connexion à MongoDB : {e}")
            raise

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Envoie un message lorsqu'un membre quitte le serveur."""
        if member.bot:
            return

        try:
            config = self.collection.find_one({"guild_id": member.guild.id})
            if config and "channel_id" in config:
                channel = member.guild.get_channel(config["channel_id"])
                if channel:
                    await channel.send(f"**{member.name}** a quitté le serveur... 😢 À la prochaine !")
                else:
                    logging.warning(f"Salon de départ introuvable (ID: {config['channel_id']}) pour le serveur {member.guild.name}.")
        except Exception as e:
            logging.error(f"Erreur lors de l'envoi du message de départ : {e}")

    @app_commands.command(name="set-leave-channel", description="Définit le salon où les messages de départ seront envoyés.")
    @app_commands.describe(channel="Le salon textuel pour les messages de départ")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_leave_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Configure le salon de départ."""
        try:
            self.collection.update_one(
                {"guild_id": interaction.guild_id},
                {"$set": {"channel_id": channel.id}},
                upsert=True
            )
            await interaction.response.send_message(f"✅ Les messages de départ seront envoyés dans {channel.mention}.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erreur lors de la configuration du salon de départ : {e}")
            await interaction.response.send_message("Une erreur est survenue lors de la configuration.", ephemeral=True)

    @app_commands.command(name="test-leave", description="Simule un départ pour tester le message d'au revoir.")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.on_member_remove(interaction.user)
        await interaction.followup.send("Test de départ effectué (vérifie le salon configuré).")

async def setup(bot):
    await bot.add_cog(LeaveServer(bot))