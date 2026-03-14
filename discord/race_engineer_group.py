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
import asyncio
from collections import defaultdict

import discord
import matplotlib.pyplot as plt
import matplotlib.ticker as tick
import redis.asyncio as redis
from discord import app_commands
from dotenv import load_dotenv

# plotting tools
import fastf1.plotting
from labellines import labelLines

from utils import *

# --- Constants ---
COMPOUND_ORDER = ["WET", "INTERMEDIATE", "SOFT", "MEDIUM", "HARD"]
GAP_CONFIG = {
    "front": {
        "title": "Gap in Front",
        "race": lambda t: t.get("IntervalToPositionAhead", {}).get("Value", ""),
        "quali": lambda t, part: t["Stats"][part - 1].get("TimeDifftoPositionAhead", ""),
        "practice": lambda t: t.get("TimeDiffToPositionAhead", ""),
    },
    "lead": {
        "title": "Gap to Leader",
        "race": lambda t: t.get("GapToLeader", ""),
        "quali": lambda t, part: t["Stats"][part - 1].get("TimeDiffToFastest", ""),
        "practice": lambda t: t.get("TimeDiffToFastest", ""),
    },
}

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
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
    sessionInfo = await redis_client.json().get("SessionInfo")
    timingDataF1 = await redis_client.json().get("TimingDataF1")

    drivers = timingDataF1["Lines"]
    session_type = sessionInfo["Type"]

    if session_type in ["Race", "Sprint"]:
        filter_key = "Retired"
    elif session_type in ["Qualifying", "Sprint Shootout"]:
        filter_key = "KnockedOut"
    else:
        # In other sessions (e.g., Practice), all drivers are considered active
        return list(drivers.keys())

    return [num for num, data in drivers.items() if not data[filter_key]]

def _get_driver_style(driverList):
    """Creates a unique visual style for each driver."""
    return {
        key: {
            "color": f"#{info['TeamColour']}",
            "linestyle": ["solid", "dashed"][idx % 2],
        }
        for idx, (key, info) in enumerate(
            sorted(driverList.items(), key=lambda item: item[1]["TeamColour"])
        )
    }

def _plot_driver_position(ax, driver_info, lap_series, style):
    """Plots the position data for a single driver."""
    drv, info = driver_info
    lap_no = list(range(len(lap_series[drv]["LapPosition"]) + 1))
    lap_pos = [int(i) for i in lap_series[drv]["LapPosition"]]
    lap_pos.append(int(info['Line']))
    ax.plot(lap_no, lap_pos, label=info["Tla"], **style)
    return max(lap_no) if lap_no else 0

def plot_position_change(sessionInfo, driverList, lapSeries):
    # --- Plotting Setup ---
    fig, ax = plt.subplots(figsize=(12.0, 6.0))
    fig.suptitle(f"{sessionInfo['Meeting']['Name']} {sessionInfo['Name']} - Position Change")

    driver_style = _get_driver_style(driverList)

    # --- Plotting Loop ---
    xvals = []
    for driver_info in sorted(driverList.items(), key=lambda item: item[1]["TeamName"]):
        style = driver_style[driver_info[0]]
        last_lap = _plot_driver_position(ax, driver_info, lapSeries, style)
        xvals.append(last_lap)

    # --- Axis Configuration ---
    ax.set_ylim([len(driver_style.items())+1, 0])
    ax.set_yticks(list({1, 2, 3, 10}.union({1, len(driverList)})))
    ax.set_xlabel("LAP")
    ax.set_ylabel("POS")
    ax.xaxis.set_major_locator(tick.MaxNLocator(integer=True))
    ax.grid(axis="x", linestyle="--")

    # --- Final Touches ---
    fig.tight_layout()
    labelLines(ax.get_lines(), align=False, xvals=xvals)

    return fig
class RaceEngineerGroup(app_commands.Group):
    """Slash command group for real-time race engineering data."""

    def __init__(self, task_semaphore: asyncio.Semaphore = asyncio.Semaphore(1)):
        """
        Initializes the RaceEngineerGroup.

        Args:
            task_semaphore (asyncio.Semaphore, optional): A semaphore to limit
                concurrent plotting tasks. Defaults to a semaphore with a value of 1.
        """
        super().__init__(
            name="race-engineer", description="Commands for the Race Engineer."
        )
        log.info("Race Engineer command group initialized.")
        # Lock to prevent race conditions when creating the position change plot.
        self.position_change_lock = asyncio.Lock()
        # Semaphore to limit the number of concurrent plotting tasks.
        self.task_semaphore = task_semaphore

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
        await interaction.response.defer(ephemeral=True, thinking=True)
        # --- Data Fetching ---
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        TyreStintSeries = await redis_client.json().get("TyreStintSeries")
        driverList = await redis_client.json().get("DriverList")
        active_driver = await get_active_driver()

        # --- Data Processing ---
        driver_current_stint = {
            driverList[RacingNumber]["BroadcastName"]: stint[-1]
            for RacingNumber, stint in TyreStintSeries["Stints"].items()
            if len(stint) > 0 and RacingNumber in active_driver
        }

        # --- Embed Creation ---
        # Group drivers by compound
        compound_groups = defaultdict(list)
        for driver, stint in driver_current_stint.items():
            compound_groups[stint["Compound"]].append((driver, stint))

        # Sort drivers within each group by tyre age and create embeds
        embeds = []
        for compound in sorted(compound_groups.keys(), key=lambda c: COMPOUND_ORDER.index(c) if c in COMPOUND_ORDER else 99):
            stints = sorted(compound_groups[compound], key=lambda x: x[1]["TotalLaps"])
            embed = discord.Embed(
                title=compound,
                color=(msgStyle["compoundColor"].get(compound)),
            )
            for driver, stint in stints:
                embed.add_field(name=driver, value=stint["TotalLaps"], inline=True)
            embeds.append(embed)

        await interaction.followup.send(embeds=embeds, ephemeral=True)

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
        await self._timing_gap_embed(interaction, "front")

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
        await self._timing_gap_embed(interaction, "lead")

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

        # --- Caching and Plot Generation ---
        # To prevent overloading the bot with plot generation requests, this command
        # uses a caching mechanism with a double-checked lock pattern.
        cache_key = f"{sessionInfo['Meeting']['Name']}_{sessionInfo['Name']}_Position Change.png"
        cached_bytes = await redis_client.get(cache_key)
        bio = None

        if cached_bytes:
            bio = io.BytesIO(cached_bytes)
        else:
            async with self.position_change_lock:
                # Re-check cache after acquiring lock to prevent race conditions
                cached_bytes = await redis_client.get(cache_key)
                if cached_bytes:
                    bio = io.BytesIO(cached_bytes)
                else:
                    async with self.task_semaphore:
                        # Generate the plot in a separate thread to avoid blocking
                        fig = await asyncio.to_thread(
                            plot_position_change, sessionInfo, driverList, lapSeries
                        )
                        if fig:
                            bio = io.BytesIO()
                            fig.savefig(bio, dpi=700, format="png")
                            bio.seek(0)
                            # Cache plot for 1 min during live race, 24h after
                            ttl = 60 if sessionInfo['ArchiveStatus']["Status"] != "Complete" else 86400
                            await redis_client.set(cache_key, bio.getvalue(), ex=ttl)

        # --- Send Response ---
        if bio:
            attachment = discord.File(bio, filename=cache_key)
            await interaction.followup.send(file=attachment)
        else:
            # Handle case where plot generation fails
            await interaction.followup.send(
                content="Sorry, the position change plot could not be generated at this time.",
                ephemeral=True,
            )
        return

    @app_commands.command(
        name="help", description="Shows a list of all available race engineer commands."
    )
    async def help_commands(self, interaction: discord.Interaction):
        """Displays a helpful message listing all race engineer commands."""
        log.info(f"Command '/race-engineer help' invoked by {interaction.user}")

        group_id = interaction.data.get("id")

        embed = discord.Embed(
            title="Race Engineer Commands",
            description="Here are all the commands available in the race-engineer group:",
            color=discord.Color.blurple(),
        )

        for cmd in self.commands:
            # Format: </group-name subcommand-name:group-id>
            cmd_mention = f"</{self.name} {cmd.name}:{group_id}>" if group_id else f"/{self.name} {cmd.name}"
            embed.add_field(
                name=cmd_mention,
                value=cmd.description,
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _get_timing_data(self):
        """Fetches and prepares timing data from Redis."""
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        # Using asyncio.gather to fetch data concurrently
        results = await asyncio.gather(
            redis_client.json().get("TimingDataF1"),
            redis_client.json().get("DriverList"),
            redis_client.json().get("SessionInfo"),
            get_active_driver(),
        )
        timingDataF1, driverList, sessionInfo, active_driver = results

        driver_timing = {
            key: value
            for key, value in timingDataF1["Lines"].items()
            if key in active_driver
        }
        driver_timing = list(
            sorted(driver_timing.items(), key=lambda item: int(driverList[item[0]].get("Line", 99)))
        )
        return timingDataF1, driverList, sessionInfo, driver_timing

    async def _timing_gap_embed(self, interaction: discord.Interaction, gap_type: str):
        """Helper function to create and send timing gap embeds."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        timingDataF1, driverList, sessionInfo, driver_timing = await self._get_timing_.data()
        config = GAP_CONFIG[gap_type]
        title = config["title"]

        embeds = []
        main_embed = discord.Embed(title=title, color=discord.Color.blurple())
        embeds.append(main_embed)

        if sessionInfo["Type"] in ["Race", "Sprint"]:
            for RacingNumber, timing in driver_timing:
                gap = config["race"](timing)
                main_embed.add_field(
                    name=driverList[RacingNumber]["BroadcastName"],
                    value=f"`{timing['LastLapTime']['Value']} ({gap})`",
                    inline=False,
                )
        elif sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
            session_part = timingDataF1["SessionPart"]
            # Append a list of large numbers to prevent index errors for later session parts.
            limit = (timingDataF1["NoEntries"] + [100] * 10)[session_part]

            driver_adv = driver_timing[:limit]
            driver_at_risk = driver_timing[limit:]

            for RacingNumber, timing in driver_adv:
                gap = config["quali"](timing, session_part)
                main_embed.add_field(
                    name=driverList[RacingNumber]["BroadcastName"],
                    value=f"`{timing['BestLapTime']['Value']} ({gap})`",
                    inline=False,
                )

            if driver_at_risk:
                at_risk_embed = discord.Embed(title="At Risk", color=discord.Color.red())
                for RacingNumber, timing in driver_at_risk:
                    gap = config["quali"](timing, session_part)
                    at_risk_embed.add_field(
                        name=driverList[RacingNumber]["BroadcastName"],
                        value=f"`{timing['BestLapTime']['Value']} ({gap})`",
                        inline=False,
                    )
                embeds.append(at_risk_embed)
        else:  # Practice
            for RacingNumber, timing in driver_timing:
                gap = config["practice"](timing)
                main_embed.add_field(
                    name=driverList[RacingNumber]["BroadcastName"],
                    value=f"`{timing['BestLapTime']['Value']} ({gap})`",
                    inline=False,
                )

        await interaction.followup.send(embeds=embeds, ephemeral=True)
