import discord
from discord.ext import commands
from discord import app_commands
import logging # --- AJOUT IMPORT LOGGING ---
import re

def parse_duration_for_ban(duration: str):
    """
    Convertit une durée (ex: 1d, 2h, 30m, 0s) en secondes.
    Spécifique pour le ban, retourne 0 si la durée est invalide ou nulle.
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

class Ban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ban", description="Bannir un membre du serveur.")
    @app_commands.describe(member="Le membre à bannir", delete_messages="Durée des messages à supprimer (ex: 1h, 2d, 0s). Max 7d.", reason="La raison du bannissement")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, delete_messages: str = "0s", *, reason: str = "Aucune raison fournie"):
        """Bannit un membre du serveur."""
        # --- LOGGING DEBUT ACTION ---
        logging.info(f"Action Ban demandée par {ctx.author} (ID: {ctx.author.id}) sur {member} (ID: {member.id}). Raison: {reason}")

        if ctx.interaction:
            await ctx.defer(ephemeral=True)

        # --- VALIDATION DES PERMISSIONS ET DE LA HIERARCHIE ---
        if member == ctx.author:
            await ctx.send("❌ Vous ne pouvez pas vous bannir vous-même.", ephemeral=True)
            return
        if member.id == ctx.guild.owner_id:
            await ctx.send("❌ Vous ne pouvez pas bannir le propriétaire du serveur.", ephemeral=True)
            return
        if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ Vous ne pouvez pas bannir un membre avec un rôle égal ou supérieur au vôtre.", ephemeral=True)
            return

        # --- PARSE ET VALIDATION DE LA DUREE DE SUPPRESSION ---
        delete_seconds = parse_duration_for_ban(delete_messages)
        if delete_seconds is None:
            await ctx.send("❌ Format de durée invalide pour `delete_messages`. Utilisez `s`, `m`, `h`, `d` (ex: `1d`, `2h30m`, `0s`).", ephemeral=True)
            return
        if delete_seconds > 604800: # 7 jours
            await ctx.send("❌ La durée de suppression des messages ne peut pas dépasser 7 jours.", ephemeral=True)
            return
        
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
            await member.ban(reason=reason, delete_message_seconds=delete_seconds)
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
            delete_msg_confirmation = f"Suppression des messages des {delete_messages}." if delete_seconds > 0 else "Aucun message supprimé."
            await ctx.send(f"✅ **{member.name}** a été banni(e). {delete_msg_confirmation} Raison : *{reason}*")
        except discord.Forbidden:
            logging.error(f"Erreur Forbidden lors du bannissement de {member}.")
            await ctx.send(f"❌ Je n'ai pas les permissions nécessaires pour bannir ce membre. (Erreur `Forbidden`)")
        except Exception as e:
            # --- LOGGING ERREUR ---
            logging.error(f"Erreur lors du bannissement de {member} : {e}")
            await ctx.send(f"❌ Une erreur est survenue lors du bannissement : {e}")

    @ban.error
    async def ban_error(self, ctx: commands.Context, error: commands.CommandError):
        """Gestionnaire d'erreurs pour la commande ban."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ **Erreur :** Argument manquant. Usage : `.ban <membre> [durée_suppr_msg] [raison]`", ephemeral=True)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"❌ **Erreur :** Membre `{error.argument}` introuvable.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Ban(bot))
