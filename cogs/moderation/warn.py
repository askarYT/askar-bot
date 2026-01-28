import discord
from discord.ext import commands
from discord import app_commands
import logging

class Warn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="warn", description="Envoyer un avertissement à un membre.")
    @app_commands.describe(member="Le membre à avertir", reason="La raison de l'avertissement (obligatoire)")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        """Avertit un membre par message privé (Raison obligatoire)."""
        # --- LOGGING DEBUT ACTION ---
        logging.info(f"Action Warn demandée par {ctx.author} (ID: {ctx.author.id}) sur {member} (ID: {member.id}). Raison: {reason}")

        # On diffère la réponse
        await ctx.defer(ephemeral=True)

        # Envoi du message privé
        sent_dm = False
        try:
            await member.send(
                f"⚠️ **Avertissement** reçu sur le serveur **{ctx.guild.name}**.\n"
                f"Raison : *{reason}*"
            )
            sent_dm = True
        except discord.Forbidden:
            # --- LOGGING WARNING MP ---
            logging.warning(f"Impossible d'envoyer le MP de warn à {member} (DMs fermés).")
            pass
        except Exception as e:
            logging.error(f"Erreur lors de l'envoi du MP de warn à {member}: {e}")

        # Confirmation et Logging
        if sent_dm:
            logging.info(f"Succès : Warn envoyé à {member}.")
            
            # --- ENVOI LOG DISCORD ---
            log_core = self.bot.get_cog("LogCore")
            if log_core:
                embed = discord.Embed(title="⚠️ Membre Averti (Warn)", color=discord.Color.yellow())
                embed.add_field(name="Membre", value=f"{member.mention} ({member.id})", inline=False)
                embed.add_field(name="Modérateur", value=ctx.author.mention, inline=False)
                embed.add_field(name="Raison", value=reason, inline=False)
                await log_core.send_log(ctx.guild, "warn", embed)

            await ctx.send(f"⚠️ **{member.name}** a été averti(e). Raison : *{reason}*")
        else:
            logging.info(f"Succès (Partiel) : Warn enregistré pour {member} (MP non envoyé).")
            await ctx.send(f"⚠️ **{member.name}** a été averti(e) (Impossible de lui envoyer un MP). Raison : *{reason}*")

    @warn.error
    async def warn_error(self, ctx, error):
        """Gestionnaire d'erreur spécifique pour la commande warn."""
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'reason':
                await ctx.send("❌ **Erreur :** Vous devez obligatoirement fournir une raison.\nUsage : `.warn @membre <raison>`", ephemeral=True)
            elif error.param.name == 'member':
                await ctx.send("❌ **Erreur :** Vous devez mentionner un membre.\nUsage : `.warn @membre <raison>`", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Warn(bot))