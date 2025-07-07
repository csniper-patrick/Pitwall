# race_engineer_group.py

import json
import discord
from discord import app_commands
import redis.asyncio as redis
from dotenv import load_dotenv
import logging
from utils import *

# Get a logger instance for this module
log = logging.getLogger(__name__)

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

class RaceEngineerGroup(app_commands.Group):
    """
    Encapsulates commands related to Race Engineering.
    This class defines a slash command group for Discord.
    """
    def __init__(self):
        # Initialize the command group with a name and description
        super().__init__(name="race-engineer", description="Commands for the Race Engineer.")
        log.info("Race Engineer command group initialized.")

    @app_commands.command(name="tyres", description="Placeholder: Check tyre status.")
    async def tyres(self, interaction: discord.Interaction):
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        currentTyres = await redis_client.json().get("CurrentTyres")
        sessionInfo = await redis_client.json().get("SessionInfo")
        await interaction.response.send_message(json.dumps(currentTyres, indent=2), ephemeral=True)
    
    @app_commands.command(name="weather", description="Track Weather")
    async def weather(self, interaction: discord.Interaction):
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        weatherData = await redis_client.json().get("WeatherData")
        response=discord.Embed(title="Track Weather")
        for key, value in weatherData.items():
            response.add_field(name=key, value=value, inline=True)
        await interaction.response.send_message(embed=response, ephemeral=True)
    
    @app_commands.command(name="timing", description="Timing")
    async def timing(self, interaction: discord.Interaction):
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        sessionInfo = await redis_client.json().get("SessionInfo")
        await interaction.response.send_message(json.dumps(timingDataF1, indent=2), ephemeral=True)
    
    @app_commands.command(name="position", description="position")
    async def position(self, interaction: discord.Interaction):
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        lapSeries = await redis_client.json().get("LapSeries")
        sessionInfo = await redis_client.json().get("SessionInfo")
        await interaction.response.send_message(json.dumps(lapSeries, indent=2), ephemeral=True)
    
    