import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import os
import logging

class JoinServer(commands.Cog):
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
            self.collection = self.db["join_server_config"]
            logging.info("Cog 'JoinServer': Connexion à MongoDB réussie.")
        except Exception as e:
            logging.error(f"Cog 'JoinServer': Erreur lors de la connexion à MongoDB : {e}")
            raise

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Envoie un message de bienvenue lorsqu'un membre rejoint le serveur."""
        if member.bot:
            return

        try:
            config = self.collection.find_one({"guild_id": member.guild.id})
            if config and "channel_id" in config:
                channel = member.guild.get_channel(config["channel_id"])
                if channel:
                    # Message de bienvenue
                    await channel.send(f"Bienvenue {member.mention} sur **{member.guild.name}** ! 🎉 Installe-toi bien !")
                else:
                    logging.warning(f"Salon de bienvenue introuvable (ID: {config['channel_id']}) pour le serveur {member.guild.name}.")
        except Exception as e:
            logging.error(f"Erreur lors de l'envoi du message de bienvenue : {e}")

    @app_commands.command(name="set-join-channel", description="Définit le salon où les messages de bienvenue seront envoyés.")
    @app_commands.describe(channel="Le salon textuel pour les messages de bienvenue")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_join_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Configure le salon de bienvenue."""
        try:
            self.collection.update_one(
                {"guild_id": interaction.guild_id},
                {"$set": {"channel_id": channel.id}},
                upsert=True
            )
            await interaction.response.send_message(f"✅ Les messages de bienvenue seront envoyés dans {channel.mention}.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erreur lors de la configuration du salon de bienvenue : {e}")
            await interaction.response.send_message("Une erreur est survenue lors de la configuration.", ephemeral=True)

    @app_commands.command(name="test-join", description="Simule une arrivée pour tester le message de bienvenue.")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_join(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.on_member_join(interaction.user)
        await interaction.followup.send("Test de bienvenue effectué (vérifie le salon configuré).")

async def setup(bot):
    await bot.add_cog(JoinServer(bot))