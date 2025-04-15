import discord
from discord import app_commands
from discord.ext import commands

class Poke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="poke", description="Envoie un ping à un utilisateur")
    async def poke(self, interaction: discord.Interaction, pseudo: discord.User):
        # Envoie le message
        await interaction.response.send_message(
            f"{pseudo.mention}, il y a {interaction.user.mention} qui te ping ! :)"
        )

async def setup(bot):
    await bot.add_cog(Poke(bot))
