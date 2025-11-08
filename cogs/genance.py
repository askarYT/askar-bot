import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient # type: ignore
import os
import logging
import re

# Liste des mots gênants et des points attribués
GENANCE_WORDS = {
    "feur": 5,
    "quoicoubeh": 10,
    "apagnan": 5,
    "quoicoubaka": 15,
    "quoikoubaka": 15,
    "baka": 10,
    "uwu": 3,
    "pagnan": 5,
    "jdene": 10,
    "lette": 10,
    "païen": 5,
    "apayan": 5,
    "kawai": 3,
}

# Liste des mots à exclure
EXCLUDED_WORDS = [
    "fleur",  # Exemple : empêche que "fleur" soit détecté comme "feur"
    "roulette",
    "toilette",
]

# Substitutions possibles pour les lettres (par exemple "e" ↔ "3")
LETTER_SUBSTITUTIONS = {
    "a": "[a@4]",
    "e": "[e3€]",
    "i": "[i1!|]",
    "o": "[o0]",
    "u": "[uü]",
    "c": "[cç]",
}

def build_advanced_pattern(word):
    """
    Construit une regex avancée pour capturer les variantes d'un mot.
    - Permet des substitutions de lettres (par exemple, "e" ↔ "3").
    - Autorise des répétitions de lettres.
    - Détecte les mots intégrés dans d'autres (par exemple, "superfeur").
    """
    pattern = ""
    for char in word:
        if char in LETTER_SUBSTITUTIONS:
            pattern += LETTER_SUBSTITUTIONS[char] + "+"
        else:
            pattern += char + "+"
    return rf"{pattern}"

class GenanceSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Connexion à MongoDB
        self.mongo_uri = os.getenv("MONGO_URI")
        if not self.mongo_uri:
            logging.error("Erreur : URI MongoDB non configurée dans les variables d'environnement.")
            raise ValueError("La variable d'environnement MONGO_URI est obligatoire.")
        
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client["askar_bot"]
            self.collection = self.db["genance_data"]
            logging.info("Connexion à MongoDB réussie.")
        except Exception as e:
            logging.error(f"Erreur lors de la connexion à MongoDB : {e}")
            raise

        # Précompilation des patterns pour les mots gênants
        self.genance_patterns = {
            word: re.compile(build_advanced_pattern(word), re.IGNORECASE)
            for word in GENANCE_WORDS
        }
        # Précompilation des patterns pour les mots exclus
        self.excluded_patterns = [
            re.compile(rf"\b{re.escape(excluded)}\b", re.IGNORECASE)
            for excluded in EXCLUDED_WORDS
        ]

    def get_user_data(self, user_id):
        """Récupère les données de gênance d'un utilisateur depuis MongoDB."""
        try:
            user_data = self.collection.find_one({"user_id": user_id})
            if not user_data:
                user_data = {"user_id": user_id, "genance_points": 0}
                self.collection.insert_one(user_data)
                logging.info(f"Création de données de gênance pour l'utilisateur {user_id}.")
            return user_data
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des données d'utilisateur : {e}")
            return {"user_id": user_id, "genance_points": 0}

    def update_user_data(self, user_id, points, word):
        """Mise à jour des points de gênance d'un utilisateur."""
        try:
            user_data = self.get_user_data(user_id)
            new_points = user_data["genance_points"] + points
            self.collection.update_one(
                {"user_id": user_id},
                {"$set": {"genance_points": new_points}},
                upsert=True
            )
            logging.info(f"Ajout de {points} points de gênance à l'utilisateur {user_id} pour le mot '{word}'. Total : {new_points}")
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour des points de gênance : {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Ajoute des points de gênance lorsqu'un mot gênant est détecté."""
        if message.author.bot:
            return

        user_id = str(message.author.id)
        content = message.content.lower()

        # Vérification des mots exclus
        for excluded_pattern in self.excluded_patterns:
            if excluded_pattern.search(content):
                logging.info(f"Message ignoré car contient un mot exclu : '{message.content}'")
                return

        # Vérification des mots gênants
        for word, pattern in self.genance_patterns.items():
            if pattern.search(content):
                self.update_user_data(user_id, GENANCE_WORDS[word], word)
                response = f"😬 {message.author.mention}, +{GENANCE_WORDS[word]} point(s) de gênance pour avoir dit **{word}** !"
                # Vérifier si le bot a la permission de répondre dans le salon
                if message.channel.permissions_for(message.guild.me).send_messages:
                    if message.channel.permissions_for(message.guild.me).mention_everyone:
                        await message.reply(response)  # Réponse avec mention du message d'origine
                    else:
                        await message.channel.send(response)  # Envoie normalement si pas de reply possible
                else:
                    # Répondre via un message privé (éphemeral) si le bot n'a pas la permission
                    await message.author.send(response)
                    logging.info(f"Mot gênant détecté : '{word}' (ou une variante) dans le message : '{message.content}'")
                break  # Arrêter après le premier mot gênant détecté

    @app_commands.command(name="genance", description="Consulte les points de gênance d'un utilisateur.")
    async def genance(self, interaction: discord.Interaction, member: discord.Member = None):
        """Affiche les points de gênance d'un utilisateur via une commande slash."""
        member = member or interaction.user
        user_id = str(member.id)
        user_data = self.get_user_data(user_id)
        points = user_data["genance_points"]
        await interaction.response.send_message(
            f"😬 {member.mention} a accumulé **{points}** point(s) de gênance.",
            ephemeral=True  # Message visible uniquement par l'utilisateur qui a exécuté la commande
        )

async def setup(bot):
    await bot.add_cog(GenanceSystem(bot))
