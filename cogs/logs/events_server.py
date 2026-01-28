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
        if before.name == after.name: return # On log seulement les changements de nom pour simplifier

        embed = discord.Embed(title="📝 Salon Modifié", description=f"{after.mention}", color=discord.Color.orange())
        embed.add_field(name="Ancien nom", value=before.name, inline=True)
        embed.add_field(name="Nouveau nom", value=after.name, inline=True)
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

async def setup(bot):
    await bot.add_cog(EventsServer(bot))