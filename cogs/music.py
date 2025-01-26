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
logger = logging.getLogger('discord')

vk_token = os.getenv('vk_token')

ffmpeg_options = {
    'executable': os.getenv('ffmpeg_path'),
    'options': '-vn',
}

@dataclass(frozen=True)
class MusicData():
    source_url:str
    music_url:str
    
@dataclass
class MusicContext():
    message: discord.WebhookMessage
    voice_client: discord.VoiceClient
    loop: bool = False
    music_queue: list[MusicData] = field(default_factory=list)

    async def cleanup(self):
        await self.message.delete()
        logger.info('del self')
        del self
        
    def __del__(self):
        logger.info('Я удалён(')



class AudioURLProcessor:

    def __init__(self, url: str):
        self.url = url

    async def process(self):
        if self.url.startswith('https://vk.com/'):
            logger.info('ЭТО ВК МУЗЫКА')
            return await self.__vk(self.url)
        if "youtube.com" in self.url or "youtu.be" in self.url:
            return await self.__youtube(self.url)
        return None

    @classmethod
    async def __youtube(cls, url: str) -> str | None:
        ydl_opts = {
            'format': 'bestaudio/best', 
            'quiet': True, 
            'noplaylist': True,
            'cookiefile': 'youtube_cookies.txt',
        }
        
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                assert info is not None
                if 'url' in info:
                    return info['url']
                elif 'formats' in info:
                    best_audio = max(info['formats'], key=lambda x: x.get('abr', 0))
                    return best_audio['url']
        
        return await asyncio.to_thread(extract)
    
    @classmethod
    async def __vk(cls, url:str) -> str | None:
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


class MusicCommentModal(discord.ui.Modal):
    def __init__(self, music_control: 'MusicControlView'):
        super().__init__(title="Комментарий к музыке")
        self.music_control = music_control
        self.add_item(discord.ui.TextInput(label="Ссылка", placeholder="https://"))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        music = self.children[0]
        self.music_control.comment_button.label = 'Добавляю музыку...'
        await self.music_control.music_context.message.edit(view=self.music_control)
        processor = AudioURLProcessor(str(music))
        url = await processor.process()
        if url:
            music = MusicData(music_url=url, source_url=str(music))
            await self.music_control.add_music(music)
            return
        self.music_control.comment_button.label = 'Добавить музыку'
        await self.music_control.music_context.message.edit(view=self.music_control)
        await interaction.followup.send(f"Некорректная ссылка!", ephemeral=True)
        
        
class MusicControlView(discord.ui.View):
    def __init__(self, music_context: MusicContext):
        super().__init__()
        self.music_context = music_context

    @discord.ui.button(label=f"Очередь: 0", style=discord.ButtonStyle.secondary, disabled=True)
    async def queue_length_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass  # Эта кнопка просто отображает состояние, она не обрабатывает нажатия

    async def get_next_music(self) -> MusicData | None:
        return self.music_context.music_queue[0] if self.music_context.music_queue else None

    async def update_queue_length(self):
        self.queue_length_button.label = f"Очередь: {len(self.music_context.music_queue)}"
        if len(self.music_context.music_queue) <= 0:
            await self.music_context.message.edit(content='Музыка кончилась(')
        await self.music_context.message.edit(view=self)
    
    async def add_music(self, music:MusicData):
        if self.comment_button.label != 'Добавить музыку':
            self.comment_button.label = 'Добавить музыку'
            await self.music_context.message.edit(view=self)        
        start = False
        if len(self.music_context.music_queue) <= 0:
            start = True
        self.music_context.music_queue.append(music)
        await self.update_queue_length()
        await self.music_context.message.edit(view=self)
        if start:
            await self.play()
            
    async def disconnect(self, message:str):
        await self.music_context.message.edit(content=message)
        await self.music_context.voice_client.disconnect()
        await self.music_context.cleanup()
    
    async def play(self): 
        music = await self.get_next_music()
        if music:
            self.music_context.voice_client.play(discord.FFmpegPCMAudio(music.music_url, **ffmpeg_options), after=self.after_play, signal_type='music')
            await self.music_context.message.edit(
                content=f"Сейчас играет: {music.source_url}",
            )
        await self.update_queue_length()

    def after_play(self, error):
        if error is not None:
            logger.info(f'{type(error)=}')
            logger.info(f'{error=}')
            raise Exception(error)
        try:
            if not self.music_context.loop and self.music_context.music_queue:
                del self.music_context.music_queue[0]
                logger.info('del!')
                logger.info(f'{len(self.music_context.music_queue)=}')
            asyncio.run_coroutine_threadsafe(self.play(), self.music_context.voice_client.loop).result()
        except Exception as e:
            raise e
    
    @discord.ui.button(label="🗑️ Clear", style=discord.ButtonStyle.danger)
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.music_context.voice_client.is_playing():
            self.music_context.voice_client.stop()
        self.music_context.music_queue = []
        await self.update_queue_length()
        await self.music_context.message.edit(content='Очередь очищена!')
        await interaction.response.defer()

    @discord.ui.button(label="⏸ Pause", style=discord.ButtonStyle.danger)
    async def toggle_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.music_context.voice_client.is_playing():
            self.music_context.voice_client.pause()
            button.label = "▶ Continue"
            button.style = discord.ButtonStyle.success
        elif self.music_context.voice_client.is_paused():
            self.music_context.voice_client.resume()
            button.label = "⏸ Pause"
            button.style = discord.ButtonStyle.danger
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="▶ Next", style=discord.ButtonStyle.success)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.music_context.loop and self.music_context.music_queue:
            del self.music_context.music_queue[0]
        
        if self.music_context.voice_client.is_playing():
            self.music_context.voice_client.stop()
        else:
            await self.play()
        await interaction.response.defer()
    
    @discord.ui.button(label="Добавить музыку", style=discord.ButtonStyle.primary)
    async def comment_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = MusicCommentModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔁 Повтор: Выкл", style=discord.ButtonStyle.secondary)
    async def repeat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.music_context.loop = not self.music_context.loop
        button.label = f"🔁 Повтор: {'Вкл' if self.music_context.loop else 'Выкл'}"
        if self.music_context.loop:
            button.style = discord.ButtonStyle.primary
        else:
            button.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
            
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
    
    async def join(self, interaction:discord.Interaction, channel_id:int = 0):
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
    
    @app_commands.command(name="start", description="Запуск бота")
    async def start(self, interaction:discord.Interaction):
        if interaction.guild is None: raise
        await interaction.response.defer()
        
        message: discord.WebhookMessage = await interaction.followup.send('Ща ща', wait=True)
        
        await message.edit(content='Подключаюсь к каналу...')
        voice_client = await self.join(interaction)
        if voice_client is None:
            await message.edit(content='Не получилось подключиться')
            return
        
        guild_context = self.guilds_queue.get(interaction.guild, None)
        if guild_context:
            await guild_context.cleanup()
        guild_context = MusicContext(message=message, voice_client=voice_client)
        
        return await message.edit(content='Жду твою говномузыку', view=MusicControlView(music_context=guild_context))

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot), guild=discord.Object(478560120138366997))