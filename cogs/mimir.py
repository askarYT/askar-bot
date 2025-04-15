import random
import discord
from discord import app_commands
from discord.ext import commands

class Mimir(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Liste mise à jour des GIFs prédéfinis
        self.gifs = [
            "https://tenor.com/view/a-mimir-gif-26093646",
            "https://tenor.com/view/goodnight-good-night-gn-nigh-night-night-gif-11750486726760890836",
            "https://tenor.com/view/a-mimir-eep-eepy-cat-sleep-gif-1640442240488704130",
        ]

    @app_commands.command(name="mimir", description="Envoie un message de souhait de sommeil avec un GIF aléatoire.")
    async def mimir(self, interaction: discord.Interaction, pseudo: discord.User = None):
        # Si aucun utilisateur n'est spécifié, utiliser l'utilisateur qui exécute la commande
        if not pseudo:
            pseudo = interaction.user

        # Sélectionne un GIF aléatoire
        selected_gif = random.choice(self.gifs)

        # Envoie le message de souhait de sommeil
        await interaction.response.send_message(
            f"{pseudo.mention}, il y a {interaction.user.mention} qui te souhaite : **[Bon Mimir !]( {selected_gif} )** 💤💤💤"

        )

async def setup(bot):
    await bot.add_cog(Mimir(bot))
