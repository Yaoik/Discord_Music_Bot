from music import AudioURLProcessor
import logging
from discord import VoiceProtocol, app_commands
from typing import cast

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s     %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

logger.info(AudioURLProcessor('https://youtu.be/XeiU8ZP7Vog'))
logger.info(AudioURLProcessor('https://youtu.be/XeiU8ZP7Vog54'))