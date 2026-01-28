import discord
from discord.ext import commands

class EventsMembers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # Log technique (compte créé quand ?)
        created_at = member.created_at.strftime("%d/%m/%Y %H:%M")
        embed = discord.Embed(title="📥 Membre Rejoint", description=f"{member.mention} (`{member.name}`)", color=discord.Color.green())
        embed.add_field(name="Compte créé le", value=created_at)
        embed.set_footer(text=f"ID: {member.id}")

        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(member.guild, "member_join", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        embed = discord.Embed(title="📤 Membre Parti", description=f"{member.mention} (`{member.name}`)", color=discord.Color.red())
        embed.set_footer(text=f"ID: {member.id}")

        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(member.guild, "member_leave", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # Changement de pseudo
        if before.nick != after.nick:
            embed = discord.Embed(title="🏷️ Pseudo Modifié", description=f"{after.mention}", color=discord.Color.blue())
            embed.add_field(name="Avant", value=before.nick or before.name, inline=True)
            embed.add_field(name="Après", value=after.nick or after.name, inline=True)
            embed.set_footer(text=f"ID: {after.id}")

            log_core = self.bot.get_cog("LogCore")
            if log_core: await log_core.send_log(after.guild, "member_update", embed)

async def setup(bot):
    await bot.add_cog(EventsMembers(bot))