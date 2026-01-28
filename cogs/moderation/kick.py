import discord
from discord.ext import commands
from discord import app_commands
import logging # --- AJOUT IMPORT LOGGING ---


class Kick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="kick", description="Exclure un membre du serveur.")
    @app_commands.describe(member="Le membre à exclure", reason="La raison de l'exclusion")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Aucune raison fournie"):
        """Exclut un membre du serveur."""
        # --- LOGGING DEBUT ACTION ---
        logging.info(f"Action Kick demandée par {ctx.author} (ID: {ctx.author.id}) sur {member} (ID: {member.id}). Raison: {reason}")

        # On diffère la réponse pour éviter que la commande plante si l'envoi du MP prend du temps (> 3s)
        await ctx.defer(ephemeral=True)

        # Envoi du message privé au membre avant l'exclusion
        try:
            await member.send(
                f"Tu as été exclu du serveur **{ctx.guild.name}**.\n"
                f"Raison : *{reason}*"
            )
        except discord.Forbidden:
            # Impossible d'envoyer le MP (DMs fermés), on continue quand même
            # --- LOGGING WARNING MP ---
            logging.warning(f"Impossible d'envoyer le MP d'exclusion à {member} (DMs fermés).")
            pass

        # Kick
        try:
            await member.kick(reason=reason)
            # --- LOGGING SUCCES ---
            logging.info(f"Succès : {member} a été exclu du serveur {ctx.guild.name}.")
            
            # --- ENVOI LOG DISCORD ---
            log_core = self.bot.get_cog("LogCore")
            if log_core:
                embed = discord.Embed(title="👢 Membre Exclu (Kick)", color=discord.Color.orange())
                embed.add_field(name="Membre", value=f"{member.mention} ({member.id})", inline=False)
                embed.add_field(name="Modérateur", value=ctx.author.mention, inline=False)
                embed.add_field(name="Raison", value=reason, inline=False)
                await log_core.send_log(ctx.guild, "kick", embed)

            # Message de confirmation
            await ctx.send(f"✅ **{member.name}** a été exclu(e). Raison : *{reason}*")
        except Exception as e:
            # --- LOGGING ERREUR ---
            logging.error(f"Erreur lors de l'exclusion de {member} : {e}")
            await ctx.send(f"❌ Une erreur est survenue lors de l'exclusion : {e}")

async def setup(bot):
    await bot.add_cog(Kick(bot))
