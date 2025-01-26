import discord
from discord.ext import commands
import asyncio
from dotenv import load_dotenv
import os
import logging
from discord import VoiceProtocol, app_commands
from typing import cast

load_dotenv()
TOKEN = str(os.getenv("DISCORD_BOT_TOKEN"))

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
logging.getLogger('discord.http').setLevel(logging.INFO)


intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@app_commands.command(name="test", description="Проигрывает муму")
async def test(interaction:discord.Interaction):
    #await interaction.followup.send(f"Сейчас играет: !!!")
    await interaction.response.send_message(f"Сейчас играет: !!!")

@bot.event
async def on_ready():
    await load_cogs()
    bot.tree.add_command(test)
    commands = await bot.tree.sync(guild=discord.Object(478560120138366997))
    logger.info(f"sync {commands}")
    await asyncio.sleep(2)
    await bot.change_presence(
        status=discord.Status.dnd,
        activity=discord.Game(name="Музыку 🎵"),
    )
    logger.info("Ready!")

async def load_cogs():
    try:
        await bot.load_extension("cogs.music")
        logger.info("✅ Cog music загружен!")
    except Exception as e:
        logger.error(f"Ошибка при загрузке cog music: {e}")

bot.run(TOKEN)
