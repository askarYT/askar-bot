import random
from discord.ext import commands

class Random(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="random")
    async def random(self, ctx, min: int = None, max: int = None):
        """
        Génère un nombre aléatoire. 

        Args:
            min (int, optional): La valeur minimale. Si non spécifiée, aucune restriction.
            max (int, optional): La valeur maximale. Si non spécifiée, aucune restriction.
        """
        # Cas 1 : Aucune restriction (pas de min ni de max)
        if min is None and max is None:
            result = random.randint(0, 1000000)  # Valeur aléatoire dans une grande plage
            await ctx.send(f'{ctx.author.name} génère un nombre aléatoire et obtient : `{result}`')
            return

        # Validation des paramètres
        if min is not None and min < 0:
            await ctx.send("La valeur minimale (`min`) ne peut pas être négative.")
            return
        if max is not None and max > 10000:
            await ctx.send("La valeur maximale (`max`) ne peut pas dépasser 10 000.")
            return
        if min is not None and max is not None and max < min:
            await ctx.send("La valeur maximale (`max`) doit être supérieure ou égale à la valeur minimale (`min`).")
            return

        # Gestion des limites (si partiellement spécifiées)
        if min is None:
            min = 0  # Valeur par défaut pour min
        if max is None:
            max = 10000  # Valeur par défaut pour max

        # Génération du nombre aléatoire
        result = random.randint(min, max)
        await ctx.send(f'{ctx.author.name} génère un nombre aléatoire entre `{min}` et `{max}` et obtient : `{result}`')

async def setup(bot):
    await bot.add_cog(Random(bot))
