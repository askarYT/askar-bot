import discord
from discord.ext import commands
from discord import app_commands
import logging # --- AJOUT IMPORT LOGGING ---


class Ban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ban", description="Bannir un membre du serveur.")
    @app_commands.describe(member="Le membre à bannir", reason="La raison du bannissement")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Aucune raison fournie"):
        """Bannit un membre du serveur."""
        # --- LOGGING DEBUT ACTION ---
        logging.info(f"Action Ban demandée par {ctx.author} (ID: {ctx.author.id}) sur {member} (ID: {member.id}). Raison: {reason}")

        # On diffère la réponse pour éviter que la commande plante si l'envoi du MP prend du temps (> 3s)
        await ctx.defer(ephemeral=True)

        # Envoi du message privé au membre avant le bannissement
        try:
            await member.send(
                f"Tu as été banni du serveur **{ctx.guild.name}**.\n"
                f"Raison : *{reason}*"
            )
        except discord.Forbidden:
            # Impossible d'envoyer le MP (DMs fermés), on continue quand même
            # --- LOGGING WARNING MP ---
            logging.warning(f"Impossible d'envoyer le MP de bannissement à {member} (DMs fermés).")
            pass

        # Bannissement
        try:
            await member.ban(reason=reason)
            # --- LOGGING SUCCES ---
            logging.info(f"Succès : {member} a été banni du serveur {ctx.guild.name}.")
            
            # --- ENVOI LOG DISCORD ---
            log_core = self.bot.get_cog("LogCore")
            if log_core:
                embed = discord.Embed(title="🔨 Membre Banni", color=discord.Color.dark_red())
                embed.add_field(name="Membre", value=f"{member.mention} ({member.id})", inline=False)
                embed.add_field(name="Modérateur", value=ctx.author.mention, inline=False)
                embed.add_field(name="Raison", value=reason, inline=False)
                await log_core.send_log(ctx.guild, "ban", embed)

            # Message de confirmation
            await ctx.send(f"✅ **{member.name}** a été banni(e). Raison : *{reason}*")
        except Exception as e:
            # --- LOGGING ERREUR ---
            logging.error(f"Erreur lors du bannissement de {member} : {e}")
            await ctx.send(f"❌ Une erreur est survenue lors du bannissement : {e}")

async def setup(bot):
    await bot.add_cog(Ban(bot))
