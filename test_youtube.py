import yt_dlp
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s     %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

url = 'https://www.youtube.com/watch?v=KLcX7D5Sj7E'

def get_audio_url(url: str):
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

logging.info(get_audio_url(url))