import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# Options yt-dlp
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'updatetime': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile' : 'cookies.txt',
}

# Options FFmpeg
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loop_states = {}  # {guild_id: True/False}

    @app_commands.command(name="join", description="Fait rejoindre le bot dans ton salon vocal")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            await interaction.response.send_message("Tu n'es pas dans un salon vocal !", ephemeral=True)
            return
        
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client is not None:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
            
        await interaction.response.send_message(f"Connecté à **{channel.name}** !")

    @app_commands.command(name="playloop", description="Joue une musique en boucle via un lien")
    @app_commands.describe(url="Le lien de la musique (YouTube, etc.)")
    async def playloop(self, interaction: discord.Interaction, url: str):
        if not interaction.user.voice:
            await interaction.response.send_message("Tu dois être dans un salon vocal pour lancer de la musique.", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        # Connexion ou déplacement du bot
        if voice_client is None:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        guild_id = interaction.guild.id
        self.loop_states[guild_id] = True

        # On répond de manière différée car yt-dlp peut prendre 1-2 secondes à analyser le lien
        await interaction.response.send_message(f"🔍 Chargement de la musique en cours...")

        async def play_next():
            if not guild_id in self.loop_states or not self.loop_states[guild_id]:
                return

            try:
                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    info = ydl.extract_info(url, download=False)
                    audio_url = info['url']
                    title = info.get('title', 'Musique')

                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
                )

                def after_playing(error):
                    if error:
                        print(f"Erreur audio : {error}")
                    
                    if self.loop_states.get(guild_id, False) and voice_client and voice_client.is_connected():
                        coro = play_next()
                        fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                        try:
                            fut.result()
                        except Exception as e:
                            print(f"Erreur lors du bouclage : {e}")

                if voice_client and not voice_client.is_playing():
                    voice_client.play(source, after=after_playing)
                    # Utilisation de edit_original_response pour modifier le message de chargement
                    await interaction.edit_original_response(content=f"🎶 Lecture en boucle de : **{title}**")

            except Exception as e:
                await interaction.edit_original_response(content=f"Une erreur est survenue lors de la lecture : `{e}`")
                self.loop_states[guild_id] = False

        await play_next()

    @app_commands.command(name="stop", description="Arrête la musique et déconnecte le bot")
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.loop_states[guild_id] = False

        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("⏹️ Musique arrêtée et déconnecté du salon vocal.")
        else:
            await interaction.response.send_message("Je ne suis pas dans un salon vocal.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Music(bot))