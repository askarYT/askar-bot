import discord
from discord.ext import commands

class EventsVoice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        log_core = self.bot.get_cog("LogCore")
        if not log_core:
            return

        # Rejoindre un salon
        if before.channel is None and after.channel is not None:
            embed = discord.Embed(title="🔊 Connexion Vocal", description=f"{member.mention} a rejoint {after.channel.mention}", color=discord.Color.green())
            embed.set_footer(text=f"ID: {member.id}")
            await log_core.send_log(member.guild, "voice_join", embed)

        # Quitter un salon
        elif before.channel is not None and after.channel is None:
            embed = discord.Embed(title="🔇 Déconnexion Vocal", description=f"{member.mention} a quitté {before.channel.mention}", color=discord.Color.red())
            embed.set_footer(text=f"ID: {member.id}")
            await log_core.send_log(member.guild, "voice_leave", embed)

        # Changer de salon (Move)
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            embed = discord.Embed(title="↔️ Déplacement Vocal", description=f"{member.mention} a changé de salon.", color=discord.Color.blue())
            embed.add_field(name="Avant", value=before.channel.mention, inline=True)
            embed.add_field(name="Après", value=after.channel.mention, inline=True)
            embed.set_footer(text=f"ID: {member.id}")
            await log_core.send_log(member.guild, "voice_move", embed)

        # Note: On ignore les changements d'état (Mute/Deafen) pour éviter le spam, 
        # sauf si tu veux les logger aussi.

    @commands.Cog.listener()
    async def on_voice_channel_status_update(self, channel, before, after):
        embed = discord.Embed(title="📝 Statut Vocal Modifié", description=f"Le statut du salon {channel.mention} a été modifié.", color=discord.Color.gold())
        embed.add_field(name="Avant", value=before if before else "*Aucun*", inline=False)
        embed.add_field(name="Après", value=after if after else "*Aucun*", inline=False)
        embed.set_footer(text=f"ID Salon: {channel.id}")

        log_core = self.bot.get_cog("LogCore")
        if log_core: await log_core.send_log(channel.guild, "voice_channel_status_update", embed)

async def setup(bot):
    await bot.add_cog(EventsVoice(bot))