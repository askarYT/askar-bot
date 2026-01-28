import discord
from discord.ext import commands
from discord import app_commands

class EventsCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- Commandes de TON Bot (Prefix) ---
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        embed = discord.Embed(title="🤖 Commande Bot (Prefix)", description=f"Commande utilisée : `{ctx.message.content}`", color=discord.Color.purple())
        embed.add_field(name="Utilisateur", value=f"{ctx.author.mention} ({ctx.author.id})", inline=True)
        embed.add_field(name="Salon", value=ctx.channel.mention, inline=True)
        
        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(ctx.guild, "command_use", embed)

    # --- Commandes de TON Bot (Slash) ---
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        embed = discord.Embed(title="🤖 Commande Bot (Slash)", description=f"Commande utilisée : `/{command.qualified_name}`", color=discord.Color.purple())
        embed.add_field(name="Utilisateur", value=f"{interaction.user.mention} ({interaction.user.id})", inline=True)
        embed.add_field(name="Salon", value=interaction.channel.mention, inline=True)

        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(interaction.guild, "command_use", embed)

    # --- Tentative de détection des AUTRES Bots ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return # On ignore les messages envoyés par les bots eux-mêmes
        
        if not message.guild:
            return

        # Liste des préfixes courants à surveiller
        common_prefixes = ('!', '?', '/', '.', ';', '$', '-')
        
        # Si le message commence par un préfixe mais N'EST PAS une commande de ton bot
        # (on vérifie si le bot a déjà traité ce message via get_context)
        if message.content.startswith(common_prefixes):
            ctx = await self.bot.get_context(message)
            if ctx.valid:
                return # C'est une commande de TON bot, déjà gérée par on_command_completion

            # C'est probablement une commande pour un autre bot
            embed = discord.Embed(title="❓ Commande Autre Bot (Détectée)", description=f"Message : `{message.content}`", color=discord.Color.light_grey())
            embed.add_field(name="Utilisateur", value=f"{message.author.mention} ({message.author.id})", inline=True)
            embed.add_field(name="Salon", value=message.channel.mention, inline=True)
            embed.set_footer(text="Détection basée sur le préfixe")

            log_core = self.bot.get_cog("LogCore")
            # On utilise le même canal "command_use"
            if log_core: await log_core.send_log(message.guild, "command_use", embed)

async def setup(bot):
    await bot.add_cog(EventsCommands(bot))