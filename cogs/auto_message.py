import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
from zoneinfo import ZoneInfo

class AutoMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = None  # ID salon où msg doit être envoyé
        self.message = None # Message automatique à envoyer
        self.daily_time = None  # Heure quotidienne de l'envoi
        self.timezone = ZoneInfo("Europe/Brussels")  # Fuseau horaire par défaut
        self.task = None    # Tâche asynchrone pour la planification de l'envoi

    @app_commands.command(name="set_message", description="Configure un message automatique dans un salon spécifique.")
    async def set_message(
        self, 
        interaction: discord.Interaction, 
        salon_id: str, 
        message: str, 
        heure: str = None, 
        timezone: str = None
    ):
        """
        Configure l'envoi automatique d'un message dans un salon.
        """
        # Vérification de l'ID du salon
        try:
            salon_id = int(salon_id)
        except ValueError:
            await interaction.response.send_message(
                "L'ID du salon doit être un nombre entier valide.", ephemeral=True
            )
            return

        # Récupération du salon
        try:
            channel = await self.bot.fetch_channel(salon_id)
        except discord.NotFound:
            await interaction.response.send_message(
                f"Salon avec l'ID `{salon_id}` introuvable.", ephemeral=True
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                f"Je n'ai pas la permission d'accéder au salon avec l'ID `{salon_id}`.", ephemeral=True
            )
            return

        # Vérifie que le canal est un salon texte
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                f"L'ID `{salon_id}` n'est pas un salon texte valide.", ephemeral=True
            )
            return

        # Vérifie et configure l'heure quotidienne si fournie
        if heure:
            try:
                self.daily_time = datetime.strptime(heure, "%H:%M").time()
            except ValueError:
                await interaction.response.send_message(
                    "L'heure doit être au format HH:MM (24h). Exemple : `14:30` pour 14h30.", ephemeral=True
                )
                return
        else:
            self.daily_time = None

        # Gestion du fuseau horaire, utilise le fuseau par défaut si non fourni
        if timezone:
            try:
                self.timezone = ZoneInfo(timezone)
            except Exception:
                await interaction.response.send_message(
                    f"Fuseau horaire invalide. Exemple de fuseaux valides : `Europe/Paris`, `UTC`, `America/New_York`.",
                    ephemeral=True
                )
                return
        else:
            self.timezone = ZoneInfo("Europe/Brussels")  # Défaut : Europe/Brussels

        self.channel_id = salon_id
        self.message = message

        # Annule l'ancien task si existant
        if self.task and not self.task.done():
            self.task.cancel()

        # Démarre le task pour l'envoi
        self.task = asyncio.create_task(self.schedule_message())
        await interaction.response.send_message(
            f"Message automatique configuré pour le salon {channel.mention} avec le message : `{message}`."
            f"{' Envoi prévu chaque jour à ' + heure + ' (' + self.timezone.key + ')' if self.daily_time else ' Envoi toutes les minutes.'}",
            ephemeral=True
        )

    @app_commands.command(name="edit_time", description="Modifie l'heure de l'envoi du message automatique.")
    async def edit_time(
        self, 
        interaction: discord.Interaction, 
        heure: str
    ):
        """
        Modifie l'heure de l'envoi du message automatique.
        """
        try:
            new_time = datetime.strptime(heure, "%H:%M").time()
            self.daily_time = new_time
            await interaction.response.send_message(
                f"Heure de l'envoi mise à jour à {new_time.strftime('%H:%M')}.", ephemeral=True
            )

            # Redémarre la tâche de planification avec la nouvelle heure
            if self.task and not self.task.done():
                self.task.cancel()
            self.task = asyncio.create_task(self.schedule_message())

        except ValueError:
            await interaction.response.send_message(
                "L'heure doit être au format HH:MM (24h). Exemple : `14:30` pour 14h30.", ephemeral=True
            )

    @app_commands.command(name="view_message", description="Affiche les détails du message automatique configuré.")
    async def view_message(self, interaction: discord.Interaction):
        """
        Affiche les détails du message automatique actuellement configuré.
        """
        if not self.message or self.channel_id is None:
            await interaction.response.send_message(
                "Aucun message automatique n'est configuré actuellement.", ephemeral=True
            )
            return

        daily_time_str = self.daily_time.strftime('%H:%M') if self.daily_time else "Non configurée"
        await interaction.response.send_message(
            f"Message automatique configuré : `{self.message}`\n"
            f"Heure de l'envoi : {daily_time_str}\n"
            f"Fuseau horaire : {self.timezone.key}", ephemeral=True
        )

    async def schedule_message(self):
        """
        Planifie le message pour l'envoyer à l'heure spécifiée ou toutes les minutes.
        """
        if self.daily_time:
            now = datetime.now(tz=self.timezone)
            target_time = datetime.combine(now.date(), self.daily_time, tzinfo=self.timezone)

            # Si l'heure cible est déjà passée aujourd'hui, planifie pour le lendemain
            if target_time <= now:
                target_time += timedelta(days=1)

            # Attente jusqu'à l'heure cible
            delay = (target_time - now).total_seconds()
            await asyncio.sleep(delay)

            # Envoie le message une première fois
            await self.send_message()

            # Ensuite, envoie chaque jour à la même heure
            while True:
                now = datetime.now(tz=self.timezone)
                next_target = datetime.combine(now.date(), self.daily_time, tzinfo=self.timezone) + timedelta(days=1)
                delay = (next_target - now).total_seconds()
                await asyncio.sleep(delay)
                await self.send_message()
        else:
            # Si aucune heure quotidienne n'est définie, envoie toutes les minutes
            while True:
                await asyncio.sleep(60)
                await self.send_message()

    async def send_message(self):
        """
        Envoie le message configuré dans le salon.
        """
        if self.channel_id and self.message:
            try:
                channel = await self.bot.fetch_channel(self.channel_id)
                await channel.send(self.message)
            except discord.NotFound:
                print(f"Salon avec l'ID `{self.channel_id}` introuvable.")
            except discord.Forbidden:
                print(f"Je n'ai pas la permission d'envoyer un message dans le salon `{self.channel_id}`.")

    @app_commands.command(name="stop_message", description="Arrête l'envoi automatique du message.")
    async def stop_message(self, interaction: discord.Interaction):
        """
        Arrête l'envoi automatique du message.
        """
        if self.channel_id is None:
            await interaction.response.send_message("Aucun message automatique n'est actuellement configuré.", ephemeral=True)
            return

        self.channel_id = None
        self.message = None
        self.daily_time = None
        self.timezone = ZoneInfo("Europe/Brussels")  # Réinitialise au fuseau par défaut

        # Arrête la tâche active
        if self.task and not self.task.done():
            self.task.cancel()
            self.task = None

        await interaction.response.send_message("L'envoi automatique du message a été arrêté.", ephemeral=True)

    @app_commands.command(name="edit_message", description="Modifie le message automatique actuel.")
    async def edit_message(self, interaction: discord.Interaction):
        """
        Permet de modifier le message automatique configuré via une modale.
        """
        if not self.message:
            await interaction.response.send_message(
                "Aucun message automatique n'est configuré actuellement. Configurez-en un avec `/set_message`.", 
                ephemeral=True
            )
            return

        class EditMessageModal(discord.ui.Modal, title="Modifier le message automatique"):
            def __init__(self, parent: AutoMessage):
                super().__init__()
                self.parent = parent
                self.message_input = discord.ui.TextInput(
                    label="Nouveau message",
                    style=discord.TextStyle.paragraph,
                    default=parent.message,
                    max_length=2000,  # Limite des messages Discord
                    required=True
                )
                self.add_item(self.message_input)

            async def on_submit(self, interaction: discord.Interaction):
                new_message = self.message_input.value
                self.parent.message = new_message  # Met à jour le message dans AutoMessage
                await interaction.response.send_message(
                    f"Message automatique mis à jour : `{new_message}`", ephemeral=True
                )

        # Affiche la modale
        await interaction.response.send_modal(EditMessageModal(self))

async def setup(bot):
    await bot.add_cog(AutoMessage(bot))