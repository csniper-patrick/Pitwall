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

async def get_active_driver():
    """
    Fetches a list of racing numbers for drivers considered "active" in the current session.

    The definition of "active" depends on the session type:
    - Race/Sprint: Drivers who have not retired.
    - Qualifying/Sprint Shootout: Drivers who have not been knocked out.
    - Practice: All drivers are considered active.

    Returns:
        list[str]: A list of racing numbers for active drivers.
    """
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
    sessionInfo = await redis_client.json().get("SessionInfo")
    timingDataF1 = await redis_client.json().get("TimingDataF1")
    if sessionInfo["Type"] in ["Race", "Sprint"]:
        
        # Filter out drivers who have retired
        active_line = dict(filter(lambda item: item[1]["Retired"] == False, timingDataF1["Lines"].items()))
        return [ RacingNumber for RacingNumber, _ in active_line.items() ]
    elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
        
        # Filter out drivers who have been knocked out
        active_line = dict(filter(lambda item: item[1]["KnockedOut"] == False, timingDataF1["Lines"].items()))
        return [ RacingNumber for RacingNumber, _ in active_line.items() ]
    else:
        
        # In other sessions (e.g., Practice), all drivers are considered active
        return [ RacingNumber for RacingNumber, _ in timingDataF1["Lines"].items() ]

class RaceEngineerGroup(app_commands.Group):
    """
    Encapsulates commands providing real-time race engineering data.
    This class defines a slash command group for Discord.
    """
    def __init__(self):
        # Initialize the command group with a name and description
        super().__init__(name="race-engineer", description="Commands for the Race Engineer.")
        log.info("Race Engineer command group initialized.")

    @app_commands.command(name="tyres", description="Shows the current tyre compound and tyre age for all active drivers.")
    async def tyres(self, interaction: discord.Interaction):
        # Establish connection to Redis and fetch necessary data
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        TyreStintSeries = await redis_client.json().get("TyreStintSeries")
        driverList = await redis_client.json().get("DriverList")
        active_driver = await get_active_driver()

        # Create a dictionary mapping active drivers to their most recent tyre stint data
        driver_current_stint = { driverList[RacingNumber]['BroadcastName']: stint[-1] for RacingNumber, stint in TyreStintSeries["Stints"].items() if len(stint) > 0 and RacingNumber in active_driver }
        response = []

        # Group drivers by their current tyre compound into separate embeds
        compounds = set([ stint["Compound"] for _, stint in driver_current_stint.items()])
        for compound in compounds:
            embed = discord.Embed(title=compound, color=msgStyle["compoundColor"][compound] if compound in msgStyle["compoundColor"] else None)
            
            # Sort drivers within each compound group by the age of their tyres (TotalLaps)
            for driver, stint in sorted( driver_current_stint.items() , key=lambda item: item[1]["TotalLaps"]):
                if stint["Compound"] == compound:
                    embed.add_field(name=driver, value=stint["TotalLaps"], inline=True)
            response.append(embed)
            
        # Sort the embeds in a logical order (Wet -> Softs) for consistent display
        response = sorted(response, key=lambda embed: ["WET", "INTERMEDIATE", "SOFT", "MEDIUM", "HARD"].index(embed.title) if embed.title in ["WET", "INTERMEDIATE", "SOFT", "MEDIUM", "HARD"] else 99 )
        await interaction.response.send_message(embeds=response, ephemeral=True)
    
    @app_commands.command(name="track_condition", description="Displays the current track status and weather conditions.")
    async def track_condition(self, interaction: discord.Interaction):
        # Fetch track status and weather data from Redis
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        weatherData = await redis_client.json().get("WeatherData")
        trackStatus = await redis_client.json().get("TrackStatus")

        # Create a Discord embed to display the current track status (e.g., Green Flag, SC Deployed)
        track_status=discord.Embed(title=f"Track Status - {trackStatus["Message"]}")

        # Create a separate Discord embed to display detailed weather information
        track_weather=discord.Embed(title="Weather")
        for key, value in weatherData.items():
            track_weather.add_field(name=key, value=value, inline=True)

        # Send both embeds in a single response
        await interaction.response.send_message(embeds=[track_status, track_weather], ephemeral=True)
    
    @app_commands.command(name="gap", description="Shows the time gap for each driver to the car directly in front.")
    async def timing_gap(self, interaction: discord.Interaction):
        # Fetch timing, driver, and session data from Redis
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")
        active_driver = await get_active_driver()

        # Create an embed to show the gap to the car ahead for each driver
        response=discord.Embed(title="Gap in Front")
        # Iterate through drivers, sorted by their position on track
        for RacingNumber, timing in sorted(timingDataF1["Lines"].items(), key=lambda item: int(item[1]['Line']) ):
            if RacingNumber not in active_driver: 
                continue
            
            # The data source for the gap differs by session type
            if sessionInfo["Type"] in ["Race", "Sprint"]:
                # In a race, use the 'IntervalToPositionAhead' field
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["LastLapTime"]["Value"]} ({timing["IntervalToPositionAhead"]['Value']})`", inline=False)
            elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
                # In qualifying, use the 'TimeDifftoPositionAhead' from the relevant session part (Q1/Q2/Q3)
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["BestLapTime"]["Value"]} ({ timing["Stats"][timingDataF1['SessionPart'] - 1 ]['TimeDifftoPositionAhead'] })`", inline=False)
        await interaction.response.send_message(embed=response, ephemeral=True)
    
    @app_commands.command(name="interval", description="Shows the time interval for each driver to the race leader.")
    async def timing_interval(self, interaction: discord.Interaction):
        # Fetch timing, driver, and session data from Redis
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")
        active_driver = await get_active_driver()

        # Create an embed to show the interval to the leader for each driver
        response=discord.Embed(title="Gap to Leader")
        # Iterate through drivers, sorted by their position on track
        for RacingNumber, timing in sorted(timingDataF1["Lines"].items(), key=lambda item: int(item[1]['Line']) ):
            if RacingNumber not in active_driver: 
                continue
            
            # The data source for the interval differs by session type
            if sessionInfo["Type"] in ["Race", "Sprint"]:
                # In a race, use the 'GapToLeader' field
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing['LastLapTime']['Value']} ({timing['GapToLeader']})`", inline=False)
            elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
                # In qualifying, use 'TimeDiffToFastest' from the relevant session part (Q1/Q2/Q3)
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing['BestLapTime']['Value']} ({timing['Stats'][timingDataF1['SessionPart'] - 1 ]['TimeDiffToFastest']})`", inline=False)
        await interaction.response.send_message(embed=response, ephemeral=True)

    
    