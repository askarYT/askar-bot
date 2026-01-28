import discord
from discord.ext import commands

class EventsServer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- SALONS ---
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed = discord.Embed(title="📂 Salon Créé", description=f"{channel.mention} (`{channel.name}`)", color=discord.Color.green())
        embed.add_field(name="Type", value=str(channel.type))
        embed.set_footer(text=f"ID: {channel.id}")
        
        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(channel.guild, "channel_create", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed = discord.Embed(title="🗑️ Salon Supprimé", description=f"`{channel.name}`", color=discord.Color.red())
        embed.set_footer(text=f"ID: {channel.id}")
        
        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(channel.guild, "channel_delete", embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        # On log les changements de nom et de sujet (topic)
        if before.name == after.name and getattr(before, 'topic', None) == getattr(after, 'topic', None):
            return

        embed = discord.Embed(title="📝 Salon Modifié", description=f"{after.mention}", color=discord.Color.orange())
        if before.name != after.name:
            embed.add_field(name="Nom", value=f"**Avant:** {before.name}\n**Après:** {after.name}", inline=False)
        if getattr(before, 'topic', None) != getattr(after, 'topic', None):
            embed.add_field(name="Sujet", value=f"**Avant:** {before.topic}\n**Après:** {after.topic}", inline=False)
            
        embed.set_footer(text=f"ID: {after.id}")

        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(after.guild, "channel_update", embed)

    # --- RÔLES ---
    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        embed = discord.Embed(title="🛡️ Rôle Créé", description=f"{role.mention} (`{role.name}`)", color=discord.Color.green())
        embed.set_footer(text=f"ID: {role.id}")

        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(role.guild, "role_create", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        embed = discord.Embed(title="🗑️ Rôle Supprimé", description=f"`{role.name}`", color=discord.Color.red())
        embed.set_footer(text=f"ID: {role.id}")

        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(role.guild, "role_delete", embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if before.name == after.name: return

        embed = discord.Embed(title="📝 Rôle Modifié", description=f"{after.mention}", color=discord.Color.orange())
        embed.add_field(name="Ancien nom", value=before.name, inline=True)
        embed.add_field(name="Nouveau nom", value=after.name, inline=True)
        embed.set_footer(text=f"ID: {after.id}")

        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(after.guild, "role_update", embed)

    # --- SERVEUR (GUILD) ---
    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        embed = discord.Embed(title="⚙️ Paramètres Serveur Modifiés", color=discord.Color.gold())
        changes = False

        if before.name != after.name:
            embed.add_field(name="Nom du serveur", value=f"**Avant:** {before.name}\n**Après:** {after.name}", inline=False)
            changes = True
        
        if before.description != after.description:
            embed.add_field(name="Description", value=f"**Avant:** {before.description}\n**Après:** {after.description}", inline=False)
            changes = True

        if before.icon != after.icon:
            embed.add_field(name="Icône", value="L'icône du serveur a changé.", inline=False)
            changes = True

        if changes:
            log_core = self.bot.get_cog("LogCore")
            if log_core: await log_core.send_log(after, "guild_update", embed)

    # --- AUTOMOD ---
    @commands.Cog.listener()
    async def on_automod_rule_create(self, rule):
        embed = discord.Embed(title="🤖 Règle AutoMod Créée", description=f"**Nom:** {rule.name}\n**Créateur:** {rule.creator}", color=discord.Color.green())
        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(rule.guild, "automod_update", embed)

    @commands.Cog.listener()
    async def on_automod_rule_delete(self, rule):
        embed = discord.Embed(title="🤖 Règle AutoMod Supprimée", description=f"**Nom:** {rule.name}", color=discord.Color.red())
        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(rule.guild, "automod_update", embed)

    @commands.Cog.listener()
    async def on_automod_rule_update(self, rule):
        # Note: L'événement on_automod_rule_update ne donne pas 'before' et 'after' facilement dans toutes les versions,
        # mais on peut logger qu'une modification a eu lieu.
        embed = discord.Embed(title="🤖 Règle AutoMod Modifiée", description=f"**Nom:** {rule.name}", color=discord.Color.orange())
        # On essaie d'afficher les actions
        actions = ", ".join([str(a.type) for a in rule.actions])
        embed.add_field(name="Actions configurées", value=actions or "Aucune", inline=False)
        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(rule.guild, "automod_update", embed)

async def setup(bot):
    await bot.add_cog(EventsServer(bot))