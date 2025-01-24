from dotenv import load_dotenv
import os
import logging
import vk_api

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s     %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


vk_token = os.getenv('vk_token')

def get_vk_audio_url(url:str):
    # https://vk.com/audio-2001578809_94578809
    try:
        track_id = url.split('audio-')[1]
        vk_user_id, vk_track_id = track_id.split('_')
    except IndexError:
        logger.info("Неверный формат ссылки.")
        return None
    
    vk_session = vk_api.VkApi(token=vk_token)
    vk = vk_session.get_api()
    logger.info(vk_session.scope)
    logger.info(vk)
    try:
        audio_info = vk.audio.getById(audios=[f'{vk_user_id}_{vk_track_id}'])[0]
        audio_url = audio_info['url']
        logger.info(f'{audio_url=}')
        return audio_url
    except vk_api.exceptions.ApiError as e:
        logger.info(f'{e=}')
        return None
    
logger.info(get_vk_audio_url('https://vk.com/audio-2001578809_94578809'))