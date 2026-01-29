import discord
from discord.ext import commands
from discord import app_commands
import logging # --- AJOUT IMPORT LOGGING ---
import re

def parse_duration_for_softban(duration: str):
    """
    Convertit une durée (ex: 1d, 2h, 30m, 0s) en secondes.
    Spécifique pour le softban, retourne 0 si la durée est invalide ou nulle.
    """
    if duration.strip() in ['0', '0s']:
        return 0
    regex = re.compile(r"(\d+)([smhd])")
    matches = regex.findall(duration.lower())
    if not matches:
        return None
    total_seconds = 0
    for value, unit in matches:
        if unit == 's': total_seconds += int(value)
        elif unit == 'm': total_seconds += int(value) * 60
        elif unit == 'h': total_seconds += int(value) * 3600
        elif unit == 'd': total_seconds += int(value) * 86400
    return total_seconds

class Softban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="softban", description="Ban puis unban un membre pour supprimer ses messages récents.")
    @app_commands.describe(member="Le membre à softban", delete_duration="Durée des messages à supprimer (défaut: 7d, max: 7d)", reason="La raison du softban")
    @commands.has_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, delete_duration: str = "7d", *, reason: str = "Aucune raison fournie"):
        """Bannit puis débannit un membre pour effacer ses messages."""
        # --- LOGGING DEBUT ACTION ---
        logging.info(f"Action Softban demandée par {ctx.author} (ID: {ctx.author.id}) sur {member} (ID: {member.id}). Raison: {reason}")

        if ctx.interaction:
            await ctx.defer(ephemeral=True)

        # --- VALIDATION DES PERMISSIONS ET DE LA HIERARCHIE ---
        if member == ctx.author:
            await ctx.send("❌ Vous ne pouvez pas vous softban vous-même.", ephemeral=True)
            return
        if member.id == ctx.guild.owner_id:
            await ctx.send("❌ Vous ne pouvez pas softban le propriétaire du serveur.", ephemeral=True)
            return
        if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ Vous ne pouvez pas softban un membre avec un rôle égal ou supérieur au vôtre.", ephemeral=True)
            return

        # --- PARSE ET VALIDATION DE LA DUREE DE SUPPRESSION ---
        if "all" in delete_duration.lower():
             await ctx.send("ℹ️ L'option 'all' n'est pas supportée par Discord. La durée maximale de suppression est de 7 jours (`7d`), qui sera appliquée.", ephemeral=True)
             delete_seconds = 604800 # On met le max si l'utilisateur demande "all"
        else:
            delete_seconds = parse_duration_for_softban(delete_duration)
            if delete_seconds is None:
                await ctx.send("❌ Format de durée invalide pour `delete_duration`. Utilisez `s`, `m`, `h`, `d` (ex: `1d`, `2h30m`, `0s`).", ephemeral=True)
                return
            if delete_seconds > 604800: # 7 jours
                await ctx.send("❌ La durée de suppression des messages ne peut pas dépasser 7 jours. C'est une limite de Discord.", ephemeral=True)
                return
        
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
            # Ban avec suppression des messages
            await member.ban(reason=f"Softban: {reason}", delete_message_seconds=delete_seconds)
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
            delete_msg_confirmation = f"Suppression des messages des {delete_duration}." if delete_seconds > 0 else "Aucun message supprimé."
            await ctx.send(f"✅ **{member.name}** a été softban. {delete_msg_confirmation} Raison : *{reason}*")
        except discord.Forbidden:
            logging.error(f"Erreur Forbidden lors du softban de {member}.")
            await ctx.send(f"❌ Je n'ai pas les permissions nécessaires pour effectuer un softban sur ce membre. (Erreur `Forbidden`)")
        except Exception as e:
            # --- LOGGING ERREUR ---
            logging.error(f"Erreur lors du softban de {member} : {e}")
            await ctx.send(f"❌ Une erreur est survenue lors du softban : {e}")

    @softban.error
    async def softban_error(self, ctx: commands.Context, error: commands.CommandError):
        """Gestionnaire d'erreurs pour la commande softban."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ **Erreur :** Argument manquant. Usage : `.softban <membre> [durée_suppr] [raison]`", ephemeral=True)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"❌ **Erreur :** Membre `{error.argument}` introuvable.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Softban(bot))
