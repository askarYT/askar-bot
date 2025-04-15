from discord.ext import commands

class Ping(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Affiche la latence du bot.")
    async def ping(self, ctx):
        """Répond avec 'Pong!' et la latence."""
        latency = round(self.bot.latency * 1000)  # Latence en millisecondes
        await ctx.send(f"Pong! {latency}ms")

async def setup(bot):
    await bot.add_cog(Ping(bot))
