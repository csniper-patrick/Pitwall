# race_engineer_group.py
"""
Discord bot commands for the Race Engineer role.

This module defines a slash command group for Discord, providing real-time race
engineering data during a motorsport event. The commands fetch live data from a
Redis instance and present it to the user in a clear and concise format, using
Discord embeds and plots.
"""

import io
import json
import logging

import discord
import matplotlib.pyplot as plt
import redis.asyncio as redis
from discord import app_commands
from dotenv import load_dotenv

# plotting tools
import fastf1.plotting
from labellines import labelLines

from utils import *

# Get a logger instance for this module
log = logging.getLogger(__name__)

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

fastf1.plotting.setup_mpl(color_scheme="fastf1")


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
    # Create a new Redis client for this request. This is the recommended practice
    # for redis-py's async client to avoid connection sharing issues.
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )
    sessionInfo = await redis_client.json().get("SessionInfo")
    timingDataF1 = await redis_client.json().get("TimingDataF1")
    if sessionInfo["Type"] in ["Race", "Sprint"]:
        # Filter out drivers who have retired
        active_line = dict(
            filter(
                lambda item: not item[1]["Retired"] and item[1]["ShowPosition"],
                timingDataF1["Lines"].items(),
            )
        )
        return [RacingNumber for RacingNumber, _ in active_line.items()]
    elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
        # Filter out drivers who have been knocked out
        active_line = dict(
            filter(
                lambda item: not item[1]["KnockedOut"] and item[1]["ShowPosition"],
                timingDataF1["Lines"].items(),
            )
        )
        return [RacingNumber for RacingNumber, _ in active_line.items()]
    else:
        # In other sessions (e.g., Practice), all drivers are considered active
        return [RacingNumber for RacingNumber, _ in timingDataF1["Lines"].items()]


class RaceEngineerGroup(app_commands.Group):
    """Slash command group for real-time race engineering data."""

    def __init__(self):
        """Initializes the RaceEngineerGroup."""
        super().__init__(
            name="race-engineer", description="Commands for the Race Engineer."
        )
        log.info("Race Engineer command group initialized.")

    @app_commands.command(
        name="tyres",
        description="Shows the current tyre compound and tyre age for all active drivers.",
    )
    async def tyres(self, interaction: discord.Interaction):
        """
        Displays the current tyre compound and age for all active drivers.

        The command groups drivers by their current tyre compound and displays them
        in separate embeds, sorted by tyre age for easy comparison.
        """
        # --- Data Fetching ---
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
        )
        TyreStintSeries = await redis_client.json().get("TyreStintSeries")
        driverList = await redis_client.json().get("DriverList")
        active_driver = await get_active_driver()

        # --- Data Processing ---
        # Create a dictionary mapping active drivers to their most recent tyre stint data.
        driver_current_stint = {
            driverList[RacingNumber]["BroadcastName"]: stint[-1]
            for RacingNumber, stint in TyreStintSeries["Stints"].items()
            if len(stint) > 0 and RacingNumber in active_driver
        }
        response = []

        # --- Embed Creation ---
        # Group drivers by their current tyre compound into separate embeds.
        compounds = set(
            stint["Compound"] for _, stint in driver_current_stint.items()
        )
        for compound in compounds:
            embed = discord.Embed(
                title=compound,
                color=(
                    msgStyle["compoundColor"].get(compound)
                ),
            )

            # Sort drivers within each compound group by the age of their tyres (TotalLaps).
            for driver, stint in sorted(
                driver_current_stint.items(), key=lambda item: item[1]["TotalLaps"]
            ):
                if stint["Compound"] == compound:
                    embed.add_field(name=driver, value=stint["TotalLaps"], inline=True)
            response.append(embed)

        # --- Response Formatting ---
        # Sort the embeds in a logical order (Wet -> Inter -> Soft -> Medium -> Hard) for consistent display.
        response = sorted(
            response,
            key=lambda embed: (
                ["WET", "INTERMEDIATE", "SOFT", "MEDIUM", "HARD"].index(embed.title)
                if embed.title in ["WET", "INTERMEDIATE", "SOFT", "MEDIUM", "HARD"]
                else 99
            ),
        )
        await interaction.response.send_message(embeds=response, ephemeral=True)

    @app_commands.command(
        name="track_condition",
        description="Displays the current track status and weather conditions.",
    )
    async def track_condition(self, interaction: discord.Interaction):
        """Displays the current track status and weather conditions in Discord embeds."""
        # --- Data Fetching ---
        # Fetch track status and weather data from Redis.
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
        )
        weatherData = await redis_client.json().get("WeatherData")
        trackStatus = await redis_client.json().get("TrackStatus")

        # --- Embed Creation ---
        # Create an embed for the current track status (e.g., Green Flag, SC Deployed).
        track_status = discord.Embed(
            title=f"Track Status - {trackStatus['Message']}",
            color=discord.Color.blurple(),
        )

        # Create a separate embed for detailed weather information.
        track_weather = discord.Embed(title="Weather", color=discord.Color.blurple())
        for key, value in weatherData.items():
            track_weather.add_field(name=key, value=value, inline=True)

        # --- Send Response ---
        # Send both embeds in a single response.
        await interaction.response.send_message(
            embeds=[track_status, track_weather], ephemeral=True
        )

    @app_commands.command(
        name="gap_in_front",
        description="Shows each driver's lap time and gap to the car ahead.",
    )
    async def timing_gap_in_front(self, interaction: discord.Interaction):
        """
        Shows each driver's lap time and gap to the car ahead.

        The data displayed is context-aware and changes based on the session type
        (Race, Qualifying, or Practice). For qualifying, it also highlights
        drivers at risk of elimination.
        """
        # --- Data Fetching ---
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
        )
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")
        active_driver = await get_active_driver()

        # --- Data Processing ---
        # Filter timing data to include only active drivers.
        driver_timing = {
            key: value
            for key, value in timingDataF1["Lines"].items()
            if key in active_driver
        }
        # Sort drivers by their position on the timing screen ('Line').
        driver_timing = list(
            sorted(driver_timing.items(), key=lambda item: int(item[1]["Line"]))
        )

        # The data displayed depends on the type of session.
        if sessionInfo["Type"] in ["Race", "Sprint"]:
            # For races, show last lap time and interval to the car ahead.
            response = discord.Embed(
                title="Gap in Front", color=discord.Color.blurple()
            )
            for RacingNumber, timing in driver_timing:
                response.add_field(
                    name=driverList[RacingNumber]["BroadcastName"],
                    value=f"`{timing['LastLapTime']['Value']} ({timing['IntervalToPositionAhead']['Value']})`",
                    inline=False,
                )
            await interaction.response.send_message(embeds=[response], ephemeral=True)

        elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
            # For qualifying, show best lap time and gap, separating drivers at risk of elimination.
            response = discord.Embed(
                title="Gap in Front", color=discord.Color.blurple()
            )

            # Determine the cutoff position for the current qualifying session part (Q1/Q2/Q3).
            # `NoEntries` holds the number of drivers advancing from each part.
            # Append a list of large numbers to prevent index errors for later session parts.
            limit = (timingDataF1["NoEntries"] + [100] * 10)[
                timingDataF1["SessionPart"]
            ]

            # Split drivers into those who are advancing and those at risk.
            driver_adv = driver_timing[:limit]
            driver_at_risk = driver_timing[limit:]

            # Create embed fields for drivers who are currently safe.
            for RacingNumber, timing in driver_adv:
                response.add_field(
                    name=driverList[RacingNumber]["BroadcastName"],
                    value=f"`{timing['BestLapTime']['Value']} ({timing['Stats'][timingDataF1['SessionPart'] - 1]['TimeDiffToPositionAhead']})`",
                    inline=False,
                )

            # If there are drivers at risk, create a separate embed for them.
            if driver_at_risk:
                at_risk = discord.Embed(title="At Risk", color=discord.Color.red())
                for RacingNumber, timing in driver_timing[limit:]:
                    at_risk.add_field(
                        name=driverList[RacingNumber]["BroadcastName"],
                        value=f"`{timing['BestLapTime']['Value']} ({timing['Stats'][timingDataF1['SessionPart'] - 1]['TimeDiffToPositionAhead']})`",
                        inline=False,
                    )
                await interaction.response.send_message(
                    embeds=[response, at_risk], ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embeds=[response], ephemeral=True
                )

        else:
            # For other sessions (e.g., Practice), show best lap time and gap to car ahead.
            response = discord.Embed(
                title="Gap in Front", color=discord.Color.blurple()
            )
            for RacingNumber, timing in driver_timing:
                response.add_field(
                    name=driverList[RacingNumber]["BroadcastName"],
                    value=f"`{timing['BestLapTime']['Value']} ({timing['TimeDiffToPositionAhead']})`",
                    inline=False,
                )
            await interaction.response.send_message(embeds=[response], ephemeral=True)

    @app_commands.command(
        name="gap_to_lead",
        description="Shows each driver's lap time and gap to the session leader.",
    )
    async def timing_gap_to_lead(self, interaction: discord.Interaction):
        """
        Shows each driver's lap time and gap to the session leader.

        The data displayed is context-aware and changes based on the session type
        (Race, Qualifying, or Practice). For qualifying, it also highlights
        drivers at risk of elimination.
        """
        # --- Data Fetching ---
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
        )
        timingDataF1 = await redis_client.json().get("TimingDataF1")
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")
        active_driver = await get_active_driver()

        # --- Data Processing ---
        # Filter timing data to include only active drivers.
        driver_timing = {
            key: value
            for key, value in timingDataF1["Lines"].items()
            if key in active_driver
        }
        # Sort drivers by their position on the timing screen ('Line').
        driver_timing = list(
            sorted(driver_timing.items(), key=lambda item: int(item[1]["Line"]))
        )

        # The data displayed depends on the type of session.
        if sessionInfo["Type"] in ["Race", "Sprint"]:
            # For races, show last lap time and gap to the leader.
            response = discord.Embed(
                title="Gap to Leader", color=discord.Color.blurple()
            )
            for RacingNumber, timing in driver_timing:
                response.add_field(
                    name=driverList[RacingNumber]["BroadcastName"],
                    value=f"`{timing['LastLapTime']['Value']} ({timing['GapToLeader']})`",
                    inline=False,
                )
            await interaction.response.send_message(embeds=[response], ephemeral=True)

        elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
            # For qualifying, show best lap time and gap, separating drivers at risk of elimination.
            response = discord.Embed(
                title="Gap to Leader", color=discord.Color.blurple()
            )

            # Determine the cutoff position for the current qualifying session part (Q1/Q2/Q3).
            # `NoEntries` holds the number of drivers advancing from each part.
            # Append a list of large numbers to prevent index errors for later session parts.
            limit = (timingDataF1["NoEntries"] + [100] * 10)[
                timingDataF1["SessionPart"]
            ]

            # Split drivers into those who are advancing and those at risk.
            driver_adv = driver_timing[:limit]
            driver_at_risk = driver_timing[limit:]

            # Create embed fields for drivers who are currently safe.
            for RacingNumber, timing in driver_adv:
                response.add_field(
                    name=driverList[RacingNumber]["BroadcastName"],
                    value=f"`{timing['BestLapTime']['Value']} ({timing['Stats'][timingDataF1['SessionPart'] - 1]['TimeDiffToFastest']})`",
                    inline=False,
                )

            # If there are drivers at risk, create a separate embed for them.
            if driver_at_risk:
                at_risk = discord.Embed(title="At Risk", color=discord.Color.red())
                for RacingNumber, timing in driver_timing[limit:]:
                    at_risk.add_field(
                        name=driverList[RacingNumber]["BroadcastName"],
                        value=f"`{timing['BestLapTime']['Value']} ({timing['Stats'][timingDataF1['SessionPart'] - 1]['TimeDiffToFastest']})`",
                        inline=False,
                    )
                await interaction.response.send_message(
                    embeds=[response, at_risk], ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embeds=[response], ephemeral=True
                )

        else:
            # For other sessions (e.g., Practice), show best lap time and gap to the fastest car.
            response = discord.Embed(
                title="Gap to Leader", color=discord.Color.blurple()
            )
            for RacingNumber, timing in driver_timing:
                response.add_field(
                    name=driverList[RacingNumber]["BroadcastName"],
                    value=f"`{timing['BestLapTime']['Value']} ({timing['TimeDiffToFastest']})`",
                    inline=False,
                )
            await interaction.response.send_message(embeds=[response], ephemeral=True)

    @app_commands.command(
        name="position",
        description="Plots each driver's position change throughout the race or sprint.",
    )
    async def position(self, interaction: discord.Interaction):
        """
        Generates and sends a plot of driver position changes throughout the session.

        This command is only available during Race or Sprint sessions. It creates a plot
        where each driver's position is tracked lap-by-lap. The generated plot is cached
        for a short period to reduce load from repeated requests.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        # --- Data Fetching ---
        # Establish a connection to Redis to fetch live session data including:
        # - DriverList: Info about each driver (name, team, color).
        # - SessionInfo: Details about the current session (e.g., Race, Sprint).
        # - LapSeries: Lap-by-lap data for each driver, including their position.
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
        )
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")
        lapSeries = await redis_client.json().get("LapSeries")

        if sessionInfo["Type"] not in ["Race", "Sprint"]:
            await interaction.followup.send(
                content="This command is only available during a Race or Sprint session.",
                ephemeral=True,
            )
            return

        # --- Plotting Setup ---
        # Initialize the matplotlib figure and axes for the plot.
        fig, ax = plt.subplots(figsize=(12.0, 6.0))

        # --- Driver Styling ---
        # Create a unique visual style (color and line style) for each driver.
        # The color is based on the team's official color. To help differentiate
        # teammates, the line style alternates between solid and dashed.
        driver_style = {
            key: {
                "color": f"#{info['TeamColour']}",
                "linestyle": ["solid", "dashed"][idx % 2],
            }
            for idx, (key, info) in enumerate(
                sorted(driverList.items(), key=lambda item: item[1]["TeamColour"])
            )
        }

        # --- Caching ---
        # Check if a cached version of the plot exists in Redis. The plot is cached
        # for 60 seconds to handle multiple requests quickly without regenerating the image.
        bio = io.BytesIO()
        cached_bytes = await redis_client.get("position_change.png")
        if cached_bytes:
            bio = io.BytesIO(cached_bytes)
        else:
            # --- Plotting Loop ---
            # Iterate through each driver to plot their position over the course of the session.
            xvals = []  # Stores the last lap number for each driver to place labels correctly.
            for drv, info in sorted(
                driverList.items(), key=lambda item: item[1]["TeamName"]
            ):
                style = driver_style[drv]
                # Extract the position for each lap from the LapSeries data.
                lap_no = list(range(len(lapSeries[drv]["LapPosition"])))
                lap_pos = [int(i) for i in lapSeries[drv]["LapPosition"]]
                xvals.append(max(lap_no) if lap_no else 0)
                # Plot the driver's position data using the pre-defined style.
                ax.plot(lap_no, lap_pos, label=info["Tla"], **style)

            # --- Axis Configuration ---
            ax.set_ylim([len(driver_style.items()) + 1, 0])  # Invert y-axis so P1 is at the top.
            ax.set_yticks([1, 5, 10, 15, 20])  # Set ticks for major positions.
            ax.set_xlabel("LAP")
            ax.set_ylabel("POS")
            ax.grid(axis="x", linestyle="--")

            # --- Final Touches ---
            fig.tight_layout()  # Adjust layout to prevent labels from being cut off.
            # Use labellines to place driver TLA (three-letter abbreviation) next to their line.
            labelLines(ax.get_lines(), align=False, xvals=xvals)

            # --- Image Generation & Caching ---
            # Save the plot to an in-memory binary stream and cache it in Redis.
            fig.savefig(bio, dpi=700, format="png")
            bio.seek(0)  # Reset stream position to the beginning.
            await redis_client.set("position_change.png", bio.getvalue(), ex=60)

        # --- Send Response ---
        # Create a discord.File object from the stream and send it.
        attachment = discord.File(bio, filename="position_change.png")
        await interaction.followup.send(file=attachment)
        return
