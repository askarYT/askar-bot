import discord
from discord import app_commands
from discord.ext import commands
from .xp_system import has_xp_permission

class Poke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="poke", description="Envoie un ping à un utilisateur")
    @has_xp_permission()
    async def poke(self, interaction: discord.Interaction, pseudo: discord.User):
        # Envoie le message
        await interaction.response.send_message(
            f"{pseudo.mention}, il y a {interaction.user.mention} qui te ping ! :)"
        )

async def setup(bot):
    await bot.add_cog(Poke(bot))
