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

    @app_commands.command(name="tyres", description="Tyres Compound")
    async def tyres(self, interaction: discord.Interaction):
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        TyreStintSeries = await redis_client.json().get("TyreStintSeries")
        driverList = await redis_client.json().get("DriverList")
        driver_current_stint = { driverList[RacingNumber]['BroadcastName']: stint[-1] for RacingNumber, stint in TyreStintSeries["Stints"].items() if len(stint) > 0 }
        response = []
        compounds = set([ stint["Compound"] for _, stint in driver_current_stint.items()])
        for compound in compounds:
            embed = discord.Embed(title=compound, color=msgStyle["compoundColor"][compound] if compound in msgStyle["compoundColor"] else None)
            for driver, stint in sorted( driver_current_stint.items() , key=lambda item: item[1]["TotalLaps"]):
                if stint["Compound"] == compound:
                    embed.add_field(name=driver, value=stint["TotalLaps"], inline=True)
            response.append(embed)
        await interaction.response.send_message(embeds=response, ephemeral=True)
    
    @app_commands.command(name="weather", description="Track Weather")
    async def weather(self, interaction: discord.Interaction):
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        weatherData = await redis_client.json().get("WeatherData")
        response=discord.Embed(title="Track Weather")
        for key, value in weatherData.items():
            response.add_field(name=key, value=value, inline=True)
        await interaction.response.send_message(embed=response, ephemeral=True)
    
    @app_commands.command(name="gap", description="Timing")
    async def timing_gap(self, interaction: discord.Interaction):
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        sessionInfo = await redis_client.json().get("SessionInfo")
        driverList = await redis_client.json().get("DriverList")
        response=discord.Embed(title="Gap in Front")
        for RacingNumber, timing in sorted(timingDataF1["Lines"].items(), key=lambda item: int(item[1]['Line']) ):
            response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=timing["IntervalToPositionAhead"]['Value'], inline=False)
            
        await interaction.response.send_message(embed=response, ephemeral=True)
    
    @app_commands.command(name="interval", description="Timing")
    async def timing_interval(self, interaction: discord.Interaction):
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        sessionInfo = await redis_client.json().get("SessionInfo")
        driverList = await redis_client.json().get("DriverList")
        response=discord.Embed(title="Gap to Leader")
        for RacingNumber, timing in sorted(timingDataF1["Lines"].items(), key=lambda item: int(item[1]['Line']) ):
            response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=timing["GapToLeader"], inline=False)
            
        await interaction.response.send_message(embed=response, ephemeral=True)
    
    @app_commands.command(name="lap_time", description="lap_time")
    async def lap_time(self, interaction: discord.Interaction):
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        lapSeries = await redis_client.json().get("LapSeries")
        sessionInfo = await redis_client.json().get("SessionInfo")
        await interaction.response.send_message(json.dumps(lapSeries, indent=2), ephemeral=True)
    
    