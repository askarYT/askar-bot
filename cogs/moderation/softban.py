import discord
from discord.ext import commands
from discord import app_commands
import logging # --- AJOUT IMPORT LOGGING ---


class Softban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="softban", description="Ban puis unban un membre pour supprimer ses messages récents.")
    @app_commands.describe(member="Le membre à softban", reason="La raison du softban")
    @commands.has_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Aucune raison fournie"):
        """Bannit puis débannit un membre pour effacer ses messages."""
        # --- LOGGING DEBUT ACTION ---
        logging.info(f"Action Softban demandée par {ctx.author} (ID: {ctx.author.id}) sur {member} (ID: {member.id}). Raison: {reason}")

        # On diffère la réponse
        await ctx.defer(ephemeral=True)

        # Envoi du message privé
        try:
            await member.send(
                f"Tu as été 'softban' du serveur **{ctx.guild.name}** (Expulsion + Suppression des messages).\n"
                f"Raison : *{reason}*\n"
                f"Tu peux rejoindre le serveur à nouveau immédiatement."
            )
        except discord.Forbidden:
            # --- LOGGING WARNING MP ---
            logging.warning(f"Impossible d'envoyer le MP de softban à {member}.")
            pass

        try:
            # Ban avec suppression des messages des 7 derniers jours (604800 secondes)
            await member.ban(reason=f"Softban: {reason}", delete_message_seconds=604800)
            # --- LOGGING ETAPE BAN ---
            logging.info(f"Softban: {member} banni temporairement (suppression messages).")
            
            # Unban immédiat
            await member.unban(reason="Fin du Softban")
            # --- LOGGING ETAPE UNBAN ---
            logging.info(f"Softban: {member} débanni immédiatement.")

            # --- ENVOI LOG DISCORD ---
            log_core = self.bot.get_cog("LogCore")
            if log_core:
                embed = discord.Embed(title="🧹 Membre Softban", color=discord.Color.orange())
                embed.add_field(name="Membre", value=f"{member.mention} ({member.id})", inline=False)
                embed.add_field(name="Modérateur", value=ctx.author.mention, inline=False)
                embed.add_field(name="Raison", value=reason, inline=False)
                await log_core.send_log(ctx.guild, "softban", embed)

            # Message de confirmation
            await ctx.send(f"✅ **{member.name}** a été softban (messages supprimés). Raison : *{reason}*")
        except Exception as e:
            # --- LOGGING ERREUR ---
            logging.error(f"Erreur lors du softban de {member} : {e}")
            await ctx.send(f"❌ Une erreur est survenue lors du softban : {e}")

async def setup(bot):
    await bot.add_cog(Softban(bot))
