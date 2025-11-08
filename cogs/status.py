import discord
from discord.ext import tasks, commands
from discord import app_commands
from pymongo import MongoClient  # type: ignore
import os
import logging
import asyncio

# ID de l'utilisateur autorisé
AUTHORIZED_USER_ID = 463639826361614336


class BotStatusManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Connexion à MongoDB
        self.mongo_uri = os.getenv("MONGO_URI")
        if not self.mongo_uri:
            logging.error("Erreur : URI MongoDB non configurée dans les variables d'environnement.")
            raise ValueError("La variable d'environnement MONGO_URI est obligatoire.")
        
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client["discord_bot"]
            self.collection = self.db["bot_status"]
            logging.info("Connexion à MongoDB réussie.")
        except Exception as e:
            logging.error(f"Erreur lors de la connexion à MongoDB : {e}")
            raise

        # Chargement des données depuis la base
        self.load_status_data()

        # Lancement du cycler si nécessaire
        self.activity_cycler.start()

    def cog_unload(self):
        self.activity_cycler.cancel()

    def load_status_data(self):
        """Charge les informations de statut et d'activités depuis la base de données."""
        data = self.collection.find_one({"bot_id": "status_data"})
        if data:
            self.activity_cycle = [discord.Activity(type=discord.ActivityType[data["type"]], name=activity)
                                   for activity in data.get("activities", [])]
            self.cycle_interval = data.get("interval", 10)
            self.current_status = discord.Status[data.get("status", "online")]
            self.current_activity = discord.Activity(type=discord.ActivityType[data.get("type", "playing")],
                                                      name=data.get("activity_text", ""))
            logging.info("Données de statut chargées avec succès.")
        else:
            # Configuration par défaut
            self.activity_cycle = []
            self.cycle_interval = 10
            self.current_status = discord.Status.online
            self.current_activity = None
            logging.info("Aucune donnée de statut trouvée. Configuration par défaut appliquée.")

    def save_status_data(self):
        """Enregistre les informations de statut et d'activités dans la base de données."""
        try:
            activities = [activity.name for activity in self.activity_cycle]
            self.collection.update_one(
                {"bot_id": "status_data"},
                {
                    "$set": {
                        "activities": activities,
                        "interval": self.cycle_interval,
                        "status": self.current_status.name,
                        "type": (self.current_activity.type.name if self.current_activity else "playing"),
                        "activity_text": (self.current_activity.name if self.current_activity else "")
                    }
                },
                upsert=True
            )
            logging.info("Données de statut enregistrées avec succès.")
        except Exception as e:
            logging.error(f"Erreur lors de l'enregistrement des données de statut : {e}")

    @tasks.loop(seconds=10)
    async def activity_cycler(self):
        """Alterner entre plusieurs activités si une liste est définie."""
        if self.activity_cycle:
            activity = self.activity_cycle.pop(0)
            await self.bot.change_presence(activity=activity, status=self.current_status)
            self.activity_cycle.append(activity)  # Remet l'activité à la fin de la liste

    @activity_cycler.before_loop
    async def before_activity_cycler(self):
        await self.bot.wait_until_ready()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Vérifie que l'utilisateur est autorisé à utiliser la commande."""
        if interaction.user.id != AUTHORIZED_USER_ID:
            await interaction.response.send_message("❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="setstatus", description="Change l'activité et le statut du bot.")
    async def set_status(self, interaction: discord.Interaction,
                        activity_type: str = None,
                        activity_text: str = None,
                        status: str = "online"):
        """Change l'activité et le statut du bot."""
        if not await self.interaction_check(interaction):
            return

        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }

        # Vérification du statut
        if status.lower() not in status_map:
            await interaction.response.send_message("❌ Statut invalide.", ephemeral=True)
            return

        # Suspension temporaire du cycler s'il est actif
        if self.activity_cycler.is_running():
            self.activity_cycler.cancel()
            logging.info("Cycler d'activités suspendu pour changement manuel.")

        self.current_status = status_map[status.lower()]

        # Si un type d'activité est défini, le texte devient obligatoire
        if activity_type:
            activity_map = {
                "playing": discord.Game,
                "listening": lambda text: discord.Activity(type=discord.ActivityType.listening, name=text),
                "watching": lambda text: discord.Activity(type=discord.ActivityType.watching, name=text),
                "competing": lambda text: discord.Activity(type=discord.ActivityType.competing, name=text),
            }

            if activity_type.lower() not in activity_map or not activity_text:
                await interaction.response.send_message(
                    "❌ Si un `activity_type` est défini, `activity_text` est obligatoire.",
                    ephemeral=True
                )
                return

            self.current_activity = activity_map[activity_type.lower()](activity_text)
        else:
            self.current_activity = None

        # Mise à jour du statut et de l'activité
        try:
            logging.info(f"Mise à jour du statut : {self.current_status}, activité : {self.current_activity}.")
            await self.bot.change_presence(activity=self.current_activity, status=self.current_status)
            logging.info("Statut et activité mis à jour avec succès.")
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour du statut/activité : {e}")
            await interaction.response.send_message("❌ Une erreur est survenue lors du changement de statut.", ephemeral=True)
            return

        # Sauvegarde dans MongoDB
        self.save_status_data()

        # Réactivation du cycler si nécessaire
        if self.activity_cycle:
            self.activity_cycler.start()
            logging.info("Cycler d'activités réactivé après changement manuel.")

        await interaction.response.send_message(
            f"✅ Statut mis à jour : {status.capitalize()}."
            + (f" Activité : {activity_type.capitalize()} {activity_text}." if self.current_activity else "")
        )

    @app_commands.command(name="setcycle", description="Alterner entre plusieurs activités à intervalles réguliers.")
    async def set_cycle(self, interaction: discord.Interaction, interval: int, activities: str):
        """
        Définit un cycle d'activités.
        - `interval` : Intervalle en secondes entre chaque changement d'activité.
        - `activities` : Liste des activités au format `type:text`, séparées par des virgules.
        """
        if not await self.interaction_check(interaction):
            return

        # Réinitialiser les activités et l'intervalle
        self.activity_cycle.clear()
        self.cycle_interval = interval

        # Parser les activités
        activity_list = activities.split(",")  # Diviser la chaîne par des virgules

        for activity in activity_list:
            try:
                activity_type, activity_text = activity.split(":", 1)
                activity_map = {
                    "playing": discord.Game,
                    "listening": lambda text: discord.Activity(type=discord.ActivityType.listening, name=text),
                    "watching": lambda text: discord.Activity(type=discord.ActivityType.watching, name=text),
                    "competing": lambda text: discord.Activity(type=discord.ActivityType.competing, name=text),
                }

                if activity_type.lower() not in activity_map:
                    raise ValueError

                # Ajouter l'activité au cycle
                self.activity_cycle.append(activity_map[activity_type.lower()](activity_text))
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Format invalide pour l'activité : {activity}. Utilise le format `type:text`.",
                    ephemeral=True,
                )
                return

        # Mettre à jour le cycle si des activités valides sont définies
        if self.activity_cycle:
            self.activity_cycler.change_interval(seconds=self.cycle_interval)
            self.save_status_data()
            await interaction.response.send_message(
                f"✅ Cycle d'activités défini avec un intervalle de {interval} secondes : {', '.join(activity_list)}."
            )
        else:
            await interaction.response.send_message("❌ Aucun cycle valide défini.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(BotStatusManager(bot))
