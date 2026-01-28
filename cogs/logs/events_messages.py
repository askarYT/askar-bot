import discord
from discord.ext import commands

class EventsMessages(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return

        embed = discord.Embed(
            title="🗑️ Message Supprimé",
            description=f"**Auteur :** {message.author.mention} ({message.author.id})\n**Salon :** {message.channel.mention}",
            color=discord.Color.red()
        )
        if message.content:
            embed.add_field(name="Contenu", value=message.content[:1024], inline=False)
        
        if message.attachments:
            embed.add_field(name="Pièces jointes", value=f"{len(message.attachments)} fichier(s)", inline=False)

        embed.set_footer(text=f"ID Message: {message.id}")

        # Appel au Core
        log_core = self.bot.get_cog("LogCore")
        if log_core:
            await log_core.send_log(message.guild, "message_delete", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild:
            return
        
        if before.content == after.content:
            return

        embed = discord.Embed(
            title="✏️ Message Modifié",
            description=f"**Auteur :** {before.author.mention} ({before.author.id})\n**Salon :** {before.channel.mention}\n[Aller au message]({after.jump_url})",
            color=discord.Color.orange()
        )
        
        # Gestion des messages trop longs
        before_content = before.content[:1020] + "..." if len(before.content) > 1020 else before.content
        after_content = after.content[:1020] + "..." if len(after.content) > 1020 else after.content

        embed.add_field(name="Avant", value=before_content or "*Vide*", inline=False)
        embed.add_field(name="Après", value=after_content or "*Vide*", inline=False)
        
        embed.set_footer(text=f"ID Message: {before.id}")

        log_core = self.bot.get_cog("LogCore")
        if log_core:
            await log_core.send_log(before.guild, "message_edit", embed)

async def setup(bot):
    await bot.add_cog(EventsMessages(bot))