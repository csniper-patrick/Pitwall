# race_engineer_group.py

import json
import discord
from discord import app_commands
import redis.asyncio as redis
from dotenv import load_dotenv
import logging
import io

# plotting tools
import matplotlib.pyplot as plt
import matplotlib.style as style
import fastf1.plotting
from labellines import labelLines

from utils import *

# Get a logger instance for this module
log = logging.getLogger(__name__)

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

fastf1.plotting.setup_mpl(color_scheme='fastf1')

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
        active_line = dict(filter(lambda item: item[1]["Retired"] == False and item[1]["ShowPosition"] == True , timingDataF1["Lines"].items()))
        return [ RacingNumber for RacingNumber, _ in active_line.items() ]
    elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
        
        # Filter out drivers who have been knocked out
        active_line = dict(filter(lambda item: item[1]["KnockedOut"] == False and item[1]["ShowPosition"] == True , timingDataF1["Lines"].items()))
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
        track_status=discord.Embed(title=f"Track Status - {trackStatus["Message"]}", color=discord.Color.blurple())

        # Create a separate Discord embed to display detailed weather information
        track_weather=discord.Embed(title="Weather", color=discord.Color.blurple())
        for key, value in weatherData.items():
            track_weather.add_field(name=key, value=value, inline=True)

        # Send both embeds in a single response
        await interaction.response.send_message(embeds=[track_status, track_weather], ephemeral=True)

    @app_commands.command(name="gap_in_front", description="Shows each driver's lap time and gap to the car ahead.")
    async def timing_gap_in_front(self, interaction: discord.Interaction):
        # Fetch timing, driver, and session data from Redis
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")
        active_driver = await get_active_driver()

        # Filter timing data to include only active drivers
        driver_timing = { key: value for key, value in timingDataF1["Lines"].items() if key in active_driver }
        # Sort the active drivers by their position on the timing screen ('Line')
        driver_timing = list(sorted(driver_timing.items(), key=lambda item: int(item[1]['Line']) ))

        # The data displayed depends on the type of session
        if sessionInfo["Type"] in ["Race", "Sprint"]:
            # For races, show last lap time and interval to the car ahead
            response=discord.Embed(title="Gap in Front", color=discord.Color.blurple())
            for RacingNumber, timing in driver_timing:
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["LastLapTime"]["Value"]} ({timing["IntervalToPositionAhead"]['Value']})`", inline=False)
            await interaction.response.send_message(embeds=[response], ephemeral=True)

        elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
            # For qualifying, show best lap time and gap. Also separate drivers at risk of elimination.
            response=discord.Embed(title="Gap in Front", color=discord.Color.blurple())

            # Determine the cutoff position for the current part of qualifying (Q1/Q2/Q3)
            limit = (timingDataF1["NoEntries"] + [100] * 10)[timingDataF1['SessionPart']]

            # Split drivers into those who are advancing and those at risk
            driver_adv=driver_timing[:limit]
            driver_at_risk=driver_timing[limit:]

            # Create embed fields for drivers who are currently safe
            for RacingNumber, timing in driver_adv:
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["BestLapTime"]["Value"]} ({ timing["Stats"][timingDataF1['SessionPart'] - 1 ]['TimeDifftoPositionAhead'] })`", inline=False)

            # If there are drivers at risk, create a separate embed for them
            if len(driver_at_risk) > 0:
                at_risk=discord.Embed(title="At Risk", color=discord.Color.red())
                for RacingNumber, timing in driver_timing[limit:]:
                    at_risk.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["BestLapTime"]["Value"]} ({ timing["Stats"][timingDataF1['SessionPart'] - 1 ]['TimeDifftoPositionAhead'] })`", inline=False)
                await interaction.response.send_message(embeds=[response, at_risk], ephemeral=True)
            else:
                # If no one is at risk, just send the main embed
                await interaction.response.send_message(embeds=[response], ephemeral=True)

        else:
            # For other sessions (e.g., Practice), show best lap time and gap to car ahead
            response=discord.Embed(title="Gap in Front", color=discord.Color.blurple())
            for RacingNumber, timing in driver_timing:
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["BestLapTime"]["Value"]} ({ timing['TimeDifftoPositionAhead'] })`", inline=False)
            await interaction.response.send_message(embeds=[response], ephemeral=True)

    @app_commands.command(name="gap_to_lead", description="Shows each driver's lap time and gap to the session leader.")
    async def timing_gap_to_lead(self, interaction: discord.Interaction):
        # Fetch timing, driver, and session data from Redis
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")
        active_driver = await get_active_driver()

        # Filter timing data to include only active drivers
        driver_timing = { key: value for key, value in timingDataF1["Lines"].items() if key in active_driver }
        # Sort the active drivers by their position on the timing screen ('Line')
        driver_timing = list(sorted(driver_timing.items(), key=lambda item: int(item[1]['Line']) ))

        # The data displayed depends on the type of session
        if sessionInfo["Type"] in ["Race", "Sprint"]:
            # For races, show last lap time and interval to the car ahead
            response=discord.Embed(title="Gap to Leader", color=discord.Color.blurple())
            for RacingNumber, timing in driver_timing:
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["LastLapTime"]["Value"]} ({timing["GapToLeader"]})`", inline=False)
            await interaction.response.send_message(embeds=[response], ephemeral=True)

        elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
            # For qualifying, show best lap time and gap. Also separate drivers at risk of elimination.
            response=discord.Embed(title="Gap to Leader", color=discord.Color.blurple())

            # Determine the cutoff position for the current part of qualifying (Q1/Q2/Q3)
            limit = (timingDataF1["NoEntries"] + [100] * 10)[timingDataF1['SessionPart']]

            # Split drivers into those who are advancing and those at risk
            driver_adv=driver_timing[:limit]
            driver_at_risk=driver_timing[limit:]

            # Create embed fields for drivers who are currently safe
            for RacingNumber, timing in driver_adv:
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["BestLapTime"]["Value"]} ({ timing["Stats"][timingDataF1['SessionPart'] - 1 ]['TimeDiffToFastest'] })`", inline=False)

            # If there are drivers at risk, create a separate embed for them
            if len(driver_at_risk) > 0:
                at_risk=discord.Embed(title="At Risk", color=discord.Color.red())
                for RacingNumber, timing in driver_timing[limit:]:
                    at_risk.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["BestLapTime"]["Value"]} ({ timing["Stats"][timingDataF1['SessionPart'] - 1 ]['TimeDiffToFastest'] })`", inline=False)
                await interaction.response.send_message(embeds=[response, at_risk], ephemeral=True)
            else:
                # If no one is at risk, just send the main embed
                await interaction.response.send_message(embeds=[response], ephemeral=True)

        else:
            # For other sessions (e.g., Practice), show best lap time and gap to car ahead
            response=discord.Embed(title="Gap to Leader", color=discord.Color.blurple())
            for RacingNumber, timing in driver_timing:
                response.add_field(name=driverList[RacingNumber]['BroadcastName'], value=f"`{timing["BestLapTime"]["Value"]} ({ timing['TimeDiffToFastest'] })`", inline=False)
            await interaction.response.send_message(embeds=[response], ephemeral=True)

    @app_commands.command(name="position", description="Plots each driver's position change throughout the race or sprint.")
    async def position(self, interaction: discord.Interaction):
        """
        Generates and sends a plot showing the position changes of each driver
        throughout the current Race or Sprint session.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        # --- Data Fetching ---
        # Establish a connection to Redis to fetch live session data.
        # - DriverList: Contains info about each driver (name, team, color).
        # - SessionInfo: Provides details about the current session (e.g., Race, Sprint).
        # - LapSeries: Contains lap-by-lap data for each driver, including their position.
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")
        lapSeries = await redis_client.json().get("LapSeries")

        if sessionInfo["Type"] not in ["Race", "Sprint"]:
            await interaction.response.send_message("This command is only available during a Race or Sprint session.", ephemeral=True)
            return
        
        # --- Plotting Setup ---
        # Initialize the matplotlib figure and axes for the plot.
        fig, ax = plt.subplots(figsize=(12.0, 6.0))

        # --- Driver Styling ---
        # Create a unique visual style (color and line style) for each driver.
        # The color is based on the team's official color. To help differentiate
        # teammates, the line style alternates between solid and dashed.
        # Sorting by team color ensures teammates are processed sequentially for this styling.
        driver_style = {
            key: {
                "color": f"#{info['TeamColour']}",
                "linestyle": ["solid", "dashed"][idx % 2], # Alternate line styles for clarity
            }
            for idx, (key, info) in enumerate(
                sorted(driverList.items(), key=lambda item: item[1]["TeamColour"])
            )
        }

        # --- Caching ---
        # Check if a cached version of the plot exists in Redis.
        # The plot is cached for 60 seconds to handle multiple requests quickly without
        # regenerating the image every time.
        bio = io.BytesIO()
        cached_bytes = await redis_client.get("position_change.png")
        if cached_bytes:
            bio = io.BytesIO(cached_bytes)
        else:
            # --- Plotting Loop ---
            # Iterate through each driver to plot their position over the course of the session.
            xvals=[] # Stores the last lap number for each driver, used to place labels correctly.
            for drv, info in sorted(driverList.items(), key=lambda item: item[1]['TeamName']):
                style = driver_style[drv]
                # Extract the position for each lap from the LapSeries data.
                lap_no = list(range(len(lapSeries[drv]['LapPosition'])))
                lap_pos = [ int(i) for i in lapSeries[drv]['LapPosition'] ]
                xvals.append(max(lap_no) if lap_no else 0) # Store the last lap for the label.
                # Plot the driver's position data using the pre-defined style.
                ax.plot(lap_no, lap_pos,
                        label=info['Tla'], **style)

            # --- Axis Configuration ---
            # Invert the y-axis so that P1 is at the top.
            ax.set_ylim([len(driver_style.items())+1, 0])
            # Set ticks for major positions for better readability.
            ax.set_yticks([1, 5, 10, 15, 20])
            ax.set_xlabel('LAP')
            ax.set_ylabel('POS')

            # --- Final Touches ---
            # Adjust layout to prevent labels from being cut off.
            fig.tight_layout()
            # Use labellines to place driver TLA (three-letter abbreviation) next to their line.
            labelLines(ax.get_lines(), align=False, xvals=xvals)

            # --- Image Generation & Caching ---
            # Save the generated plot to an in-memory binary stream (BytesIO).
            fig.savefig(bio, dpi=700, format="png")
            # Reset the stream's position to the beginning before reading.
            bio.seek(0)
            # Cache the newly generated plot in Redis for 60 seconds.
            await redis_client.set("position_change.png", bio.getvalue(), ex=60)
        
        # --- Send Response ---
        # Create a discord.File object from the stream and send it.
        attachment = discord.File(bio, filename="position_change.png")
        await interaction.followup.send(file=attachment)
        return
