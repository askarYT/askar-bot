import discord
from discord.ext import commands, tasks
from discord import app_commands
from pymongo import MongoClient
import os
import logging
from datetime import datetime, timedelta, timezone
import re

class Tempban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Connexion à MongoDB (comme dans xp_system.py)
        self.mongo_uri = os.getenv("MONGO_URI")
        if not self.mongo_uri:
            raise ValueError("La variable d'environnement MONGO_URI est obligatoire.")
            
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client["askar_bot"]
            self.collection = self.db["tempbans"]
        except Exception as e:
            logging.error(f"Cog 'Tempban': Erreur MongoDB : {e}")
            raise

        # Démarrage de la boucle de vérification
        self.check_tempbans.start()

    def cog_unload(self):
        self.check_tempbans.cancel()

    def parse_duration(self, duration: str):
        """Convertit une durée (ex: 1d, 2h, 30m) en secondes."""
        regex = re.compile(r"(\d+)([smhd])")
        matches = regex.findall(duration.lower())
        total_seconds = 0
        
        if not matches:
            return None
            
        for value, unit in matches:
            if unit == 's': total_seconds += int(value)
            elif unit == 'm': total_seconds += int(value) * 60
            elif unit == 'h': total_seconds += int(value) * 3600
            elif unit == 'd': total_seconds += int(value) * 86400
            
        return total_seconds

    @commands.hybrid_command(name="tempban", description="Bannir temporairement un membre.")
    @app_commands.describe(member="Le membre à bannir", duration="Durée du ban (ex: 1d, 2h, 30m)", delete_messages="Durée des messages à supprimer (ex: 1h, 2d, 0s). Max 7d.", reason="La raison")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx: commands.Context, member: discord.Member, duration: str, delete_messages: str = "0s", *, reason: str = "Aucune raison fournie"):
        """Bannit un membre pour une durée déterminée."""
        # --- LOGGING DEBUT ACTION ---
        logging.info(f"Action Tempban demandée par {ctx.author} (ID: {ctx.author.id}) sur {member} (ID: {member.id}). Durée: {duration}, Raison: {reason}")

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

        # --- PARSE DURATIONS ---
        seconds = self.parse_duration(duration)
        if not seconds:
            await ctx.send("❌ Format de durée invalide. Utilisez `s` (secondes), `m` (minutes), `h` (heures), `d` (jours). Ex: `1d`, `2h30m`.")
            return
        
        delete_seconds = self.parse_duration(delete_messages) if delete_messages not in ["0", "0s"] else 0
        if delete_seconds is None or delete_seconds > 604800:
            await ctx.send("❌ Durée de suppression de messages invalide ou supérieure à 7 jours.", ephemeral=True)
            return

        unban_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)

        # Envoi du MP
        try:
            await member.send(
                f"Tu as été banni temporairement du serveur **{ctx.guild.name}**.\n"
                f"Durée : **{duration}**\n"
                f"Raison : *{reason}*"
            )
        except discord.Forbidden:
            # --- LOGGING WARNING MP ---
            logging.warning(f"Impossible d'envoyer le MP de tempban à {member}.")
            pass

        # Bannissement Discord
        try:
            await member.ban(reason=f"Tempban ({duration}): {reason}", delete_message_seconds=delete_seconds)
            # --- LOGGING SUCCES BAN ---
            logging.info(f"Tempban: {member} banni sur Discord.")
        except discord.Forbidden:
            logging.error(f"Erreur Forbidden lors du tempban de {member}.")
            await ctx.send(f"❌ Je n'ai pas les permissions nécessaires pour bannir ce membre. (Erreur `Forbidden`)")
            return
        except Exception as e:
            # --- LOGGING ERREUR BAN ---
            logging.error(f"Erreur lors du tempban (action ban) de {member} : {e}")
            await ctx.send(f"❌ Impossible de bannir le membre : {e}")
            return

        # Enregistrement dans la BDD
        try:
            self.collection.insert_one({
                "guild_id": ctx.guild.id,
                "user_id": member.id,
                "unban_time": unban_time,
                "reason": reason
            })
            # --- LOGGING SUCCES DB ---
            logging.info(f"Tempban: Enregistrement DB réussi pour {member} (Fin: {unban_time}).")
        except Exception as e:
            # --- LOGGING ERREUR DB ---
            logging.error(f"Erreur lors de l'enregistrement du tempban en DB pour {member} : {e}")

        # --- ENVOI LOG DISCORD ---
        log_core = self.bot.get_cog("LogCore")
        if log_core:
            embed = discord.Embed(title="⏳ Membre Tempban", color=discord.Color.dark_red())
            embed.add_field(name="Membre", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Modérateur", value=ctx.author.mention, inline=False)
            embed.add_field(name="Durée", value=duration, inline=True)
            embed.add_field(name="Raison", value=reason, inline=False)
            await log_core.send_log(ctx.guild, "tempban", embed)

        # Message de confirmation
        delete_msg_confirmation = f"Suppression des messages des {delete_messages}." if delete_seconds > 0 else "Aucun message supprimé."
        await ctx.send(f"✅ **{member.name}** a été banni pour **{duration}**. {delete_msg_confirmation} Raison : *{reason}*")

    @tempban.error
    async def tempban_error(self, ctx: commands.Context, error: commands.CommandError):
        """Gestionnaire d'erreurs pour la commande tempban."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ **Erreur :** Argument manquant. Usage : `.tempban <membre> <durée> [durée_suppr_msg] [raison]`", ephemeral=True)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"❌ **Erreur :** Membre `{error.argument}` introuvable.", ephemeral=True)

    @tasks.loop(minutes=1)
    async def check_tempbans(self):
        """Vérifie périodiquement les bannissements expirés."""
        now = datetime.now(timezone.utc)
        # On cherche tous les bans dont la date de fin est passée (inférieure à maintenant)
        expired_bans = list(self.collection.find({"unban_time": {"$lte": now}}))

        for ban in expired_bans:
            guild = self.bot.get_guild(ban["guild_id"])
            if not guild:
                continue

            try:
                # On essaie de débannir l'utilisateur via son ID
                user = await self.bot.fetch_user(ban["user_id"])
                await guild.unban(user, reason="Fin du Tempban automatique")
                logging.info(f"Tempban expiré : {user.name} débanni du serveur {guild.name}.")
            except discord.NotFound:
                logging.warning(f"Utilisateur {ban['user_id']} introuvable pour l'unban.")
            except discord.Forbidden:
                logging.warning(f"Permission manquante pour débannir sur {guild.name}.")
            except Exception as e:
                logging.error(f"Erreur lors de l'unban automatique : {e}")
            finally:
                # On retire l'entrée de la BDD qu'il ait été débanni ou non (pour éviter de boucler sur une erreur)
                self.collection.delete_one({"_id": ban["_id"]})

    @check_tempbans.before_loop
    async def before_check_tempbans(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Tempban(bot))
