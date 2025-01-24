import discord
from discord import Guild, VoiceChannel
from discord.ext import commands
import yt_dlp
import asyncio
from dotenv import load_dotenv
import os
import logging
from discord import VoiceProtocol, app_commands
from typing import cast
import vk_api
from dataclasses import dataclass, field

load_dotenv()
logger = logging.getLogger(__name__)

vk_token = os.getenv('vk_token')

ffmpeg_options = {
    'executable': os.getenv('ffmpeg_path'),
    'options': '-vn',
}

@dataclass
class MusicContext():
    message: discord.WebhookMessage
    voice_client: discord.VoiceClient
    loop: bool = False
    queue: list[tuple[str, str]] = field(default_factory=list)
    
class MusicControlView(discord.ui.View):
    def __init__(self, music_context: MusicContext):
        super().__init__()
        self.music_context = music_context
        self.voice_client = self.music_context.voice_client
        
        audio_url = self.get_next_music()
        assert audio_url is not None
        if self.voice_client.is_playing():
            self.voice_client.stop()
        logger.info('playing')
        logger.info(self.voice_client.channel)
        logger.info(self.voice_client)
        self.voice_client.play(discord.FFmpegPCMAudio(audio_url[1], **ffmpeg_options), after=self.after_play)
        logger.info('playing')

    def get_next_music(self) -> tuple[str, str] | None:
        logger.info(f'{self.music_context.queue}')
        return self.music_context.queue.pop(0) if self.music_context.queue else None

    async def disconnect(self, message:str):
        await self.music_context.message.edit(content=message, view=None)
        await self.music_context.voice_client.disconnect()
        del self.music_context
        
    def after_play(self, error):
        if error:
            logger.error(f"Ошибка при воспроизведении: {error}")
        audio_url = self.get_next_music()
        if audio_url:
            asyncio.create_task(self.play(audio_url))
        else:
            asyncio.create_task(self.disconnect('Очередь пуста'))
    
    async def play(self, url:tuple[str, str]):
        if self.voice_client.is_playing():
            self.voice_client.stop()
        
        logger.info(f'play {url=}')
        self.voice_client.play(discord.FFmpegPCMAudio(url[1], **ffmpeg_options), after=self.after_play)
        await self.music_context.message.edit(
            content=f"Сейчас играет: {url[0]}\tДлина очереди:{len(self.music_context.queue)}",
        )
    
    @discord.ui.button(label=":recycle: Clear queue", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.voice_client.is_playing():
            self.voice_client.stop()
        self.music_context.queue = []
        await self.disconnect('Очередь очищена')

    @discord.ui.button(label="⏸ Пауза", style=discord.ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.voice_client.is_playing():
            self.voice_client.pause()
        await interaction.response.defer()

    @discord.ui.button(label="▶ Продолжить", style=discord.ButtonStyle.success)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.voice_client.is_paused():
            self.voice_client.resume()
        await interaction.response.defer()
        
    @discord.ui.button(label="▶ Next", style=discord.ButtonStyle.success)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        url = self.get_next_music()
        if url is not None:
            logger.info(f'{url[0]=}')
            await self.play(url)
            await interaction.response.defer()
        else:
            await self.disconnect('Музыка кончилась(')
            
class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guilds_queue:dict[Guild, MusicContext] = {}
        
    async def get_voice_channel(self, interaction:discord.Interaction, channel_id:int) -> None | VoiceChannel:
        if channel_id > 0:
            voice_channel = interaction.guild.get_channel(channel_id) # type: ignore
            if not voice_channel or not isinstance(voice_channel, discord.VoiceChannel):
                await interaction.response.send_message("Не удалось найти голосовой канал с таким ID.", ephemeral=True)
                return None
        else:
            if not interaction.user.voice or not interaction.user.voice.channel: # type: ignore
                await interaction.response.send_message("Вы не находитесь в голосовом канале!", ephemeral=True)
                return None
            voice_channel = cast(VoiceChannel, interaction.user.voice.channel) # type: ignore
        return voice_channel
    
    async def join(self, interaction:discord.Interaction, channel_id:int):
        voice_channel = await self.get_voice_channel(interaction, channel_id)
        
        if interaction.guild is None:
            return None
        
        if voice_channel:
            voice_client = interaction.guild.voice_client
            if isinstance(voice_client, discord.VoiceClient):
                await voice_client.move_to(voice_channel)
            else:
                await voice_channel.connect()
            voice_client = cast(discord.VoiceClient, interaction.guild.voice_client)
            return voice_client

    @app_commands.command(name="add", description="Добавляет музыку в очередь (по ссылке)")
    @app_commands.describe(url="Ссылка на видео")
    async def add(self, interaction:discord.Interaction, url:str):
        await interaction.response.defer()
        if not interaction.guild:
            await interaction.followup.send('Чёт не пошло(')
            return None
        
        music_context = self.guilds_queue.get(interaction.guild, None)
        if music_context:
            if music_context.voice_client:
                try:
                    audio_url = self.get_audio_url(url)
                    assert audio_url is not None
                    music_context.queue.append((url, audio_url))
                except Exception as e:
                    logger.error(f'{e=}')
                    return None
                await interaction.followup.send(f'Добавил url в очередь #{len(music_context.queue)}')
            else:
                del music_context
        else:
            await interaction.followup.send(f'Сначала запусти play!')
        
    
    @app_commands.command(name="play", description="Проигрывает музыку с YouTube! (я сам написал)")
    @app_commands.describe(url="Ссылка на видео", channel_id="ID канала, если нужно")
    async def play(self, interaction:discord.Interaction, url:str, channel_id:int=0):
        if interaction.guild is None: raise
        await interaction.response.defer()
        message: discord.WebhookMessage = await interaction.followup.send('Ща ща', wait=True)
        if not url.startswith('https://'):
            await message.edit(content='Некорректный URL')
            return None
        
        await message.edit(content='Получаю аудио дорожку...')
        try:
            audio_url = self.get_audio_url(url)
            assert audio_url is not None
        except Exception as e:
            await message.edit(content='Не удалось получить ссылку на аудио-дорожку')
            logger.info(f'{e=}')
            return None
        
        await message.edit(content='Подключаюсь к каналу...')
        voice_client: discord.VoiceClient = cast(discord.VoiceClient, await self.join(interaction, channel_id))
        if voice_client is None:
            await message.edit(content="❌ Не удалось подключиться к голосовому каналу.")
            return None
        
        await message.edit(content='Запускаю музыку...')

        music_context = self.guilds_queue.setdefault(interaction.guild, MusicContext(message, voice_client))
        source_url = url
        music_context.queue = [(source_url, audio_url)]
        music_context.voice_client = voice_client
        if music_context.message != message:
            await music_context.message.delete()
            music_context.message = message

        await message.edit(
            content=f"Сейчас играет: {url}",
            view=MusicControlView(music_context)
        )

    def get_vk_audio_url(self, url:str):
        # https://vk.com/audio-2001578809_94578809
        try:
            track_id = url.split('audio-')[1]
            vk_user_id, vk_track_id = track_id.split('_')
        except IndexError:
            logger.info("Неверный формат ссылки.")
            return None
        
        vk_session = vk_api.VkApi(token=vk_token)
        vk = vk_session.get_api()

        try:
            audio_info = vk.audio.getById(audios=[f'{vk_user_id}_{vk_track_id}'])[0]
            audio_url = audio_info['url']
            logger.info(f'{audio_url=}')
            return audio_url
        except vk_api.exceptions.ApiError as e:
            logger.info(f'{e=}')
            return None

    def get_audio_url(self, url:str) -> None | str:
        if url.startswith('https://vk.com/'):
            logger.info('ЭТО ВК МУЗЫКА')
            return self.get_vk_audio_url(url)
        
        if url.startswith(('https://www.youtube.com/', 'https://youtu.be/')):
            ydl_opts = {
                'format': 'bestaudio/best', 
                'quiet': True, 
                'noplaylist': True,
                'cookiefile': 'youtube_cookies.txt',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                assert info is not None
                if 'url' in info:
                    return info['url']
                elif 'formats' in info:
                    best_audio = max(info['formats'], key=lambda x: x.get('abr', 0))
                    return best_audio['url']

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot), guild=discord.Object(1227561350981619762))