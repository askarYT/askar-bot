import discord
from discord.ext import commands
from discord import app_commands
import logging # --- AJOUT IMPORT LOGGING ---

class Unban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="unban", description="Débannir un membre du serveur.")
    @app_commands.describe(user="L'utilisateur à débannir (ID ou sélection dans la liste)", reason="La raison du débannissement")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user: str, *, reason: str = "Aucune raison fournie"):
        """Débannit un membre du serveur."""
        # --- LOGGING DEBUT ACTION ---
        logging.info(f"Action Unban demandée par {ctx.author} (ID: {ctx.author.id}) pour l'entrée '{user}'. Raison: {reason}")

        # On diffère la réponse pour les interactions slash
        if ctx.interaction:
            await ctx.defer(ephemeral=True)

        user_obj = None
        
        # 1. Si l'entrée est un ID (cas de l'autocomplétion ou ID manuel)
        if user.isdigit():
            try:
                user_obj = await self.bot.fetch_user(int(user))
            except discord.NotFound:
                pass
        
        # 2. Si ce n'est pas un ID, on cherche dans la liste des bans (cas commande texte avec pseudo)
        if not user_obj:
            try:
                async for ban_entry in ctx.guild.bans(limit=None):
                    if user.lower() in ban_entry.user.name.lower() or user == str(ban_entry.user):
                        user_obj = ban_entry.user
                        break
            except Exception as e:
                # --- LOGGING ERREUR RECHERCHE ---
                logging.error(f"Erreur lors de la récupération des bans pour unban : {e}")
                await ctx.send(f"❌ Erreur lors de la récupération des bans : {e}")
                return

        if not user_obj:
            # --- LOGGING INTROUVABLE ---
            logging.warning(f"Unban: Utilisateur '{user}' introuvable ou non banni.")
            await ctx.send(f"❌ Utilisateur **{user}** introuvable ou non banni.")
            return

        # 3. Exécution du débannissement
        try:
            await ctx.guild.unban(user_obj, reason=reason)
            # --- LOGGING SUCCES ---
            logging.info(f"Succès : {user_obj} (ID: {user_obj.id}) a été débanni.")
            
            # --- ENVOI LOG DISCORD ---
            log_core = self.bot.get_cog("LogCore")
            if log_core:
                embed = discord.Embed(title="🔓 Membre Débanni", color=discord.Color.green())
                embed.add_field(name="Membre", value=f"{user_obj.name} ({user_obj.id})", inline=False)
                embed.add_field(name="Modérateur", value=ctx.author.mention, inline=False)
                embed.add_field(name="Raison", value=reason, inline=False)
                await log_core.send_log(ctx.guild, "unban", embed)

            await ctx.send(f"🔓 **{user_obj.name}** a été débanni. Raison : *{reason}*")
        except discord.NotFound:
            logging.warning(f"Unban: {user_obj} n'était pas dans la liste des bannis (NotFound).")
            await ctx.send(f"❌ **{user_obj.name}** n'est pas dans la liste des bannis.")
        except Exception as e:
            # --- LOGGING ERREUR ACTION ---
            logging.error(f"Erreur lors du débannissement de {user_obj} : {e}")
            await ctx.send(f"❌ Impossible de débannir **{user_obj.name}** : {e}")

    @unban.error
    async def unban_error(self, ctx: commands.Context, error: commands.CommandError):
        """Gestionnaire d'erreurs pour la commande unban."""
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'user':
                await ctx.send("❌ **Erreur :** Vous devez spécifier un utilisateur (Nom#Tag ou ID).\nUsage : `.unban <utilisateur> [raison]`", ephemeral=True)

    @unban.autocomplete('user')
    async def unban_autocomplete(self, interaction: discord.Interaction, current: str):
        if not interaction.guild:
            return []
            
        try:
            # Récupère la liste des bannis
            bans = [entry async for entry in interaction.guild.bans(limit=None)]
            
            # Filtre selon la saisie de l'utilisateur
            choices = [
                app_commands.Choice(name=f"{entry.user.name} ({entry.user.id})", value=str(entry.user.id))
                for entry in bans
                if current.lower() in entry.user.name.lower() or current in str(entry.user.id)
            ]
            # Discord limite à 25 choix max
            return choices[:25]
        except Exception:
            return []

async def setup(bot):
    await bot.add_cog(Unban(bot))