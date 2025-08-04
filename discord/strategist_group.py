# strategist_group.py
"""
This module defines the Discord bot commands related to race strategy for the Pitwall application.
It includes commands for retrieving F1 schedules, track maps, driver/team pace analysis,
and championship standings. The commands are organized under the '/strategist' slash
command group.

The module uses fastf1 for historical F1 data, Redis for caching and live data,
and Matplotlib/Seaborn for generating plots.
"""

# Standard library imports
import datetime
import io
import logging
import os
from typing import Optional
import asyncio

# Third-party imports
import discord
from discord import app_commands
from dotenv import load_dotenv
import fastf1
import fastf1.plotting
from fastf1.ergast import Ergast
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
import matplotlib.ticker as tick
import matplotlib.lines as mlines
import pandas as pd
import numpy as np
import redis.asyncio as redis
import seaborn as sns

# Local application imports
from utils import *

# Get a logger instance for this module
log = logging.getLogger(__name__)

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

fastf1.plotting.setup_mpl(color_scheme="fastf1")

# This directory constant is needed for the trackmap command
TRACKS_DIR = "data/tracks"

async def event_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Provide autocomplete suggestions for F1 event names.

    This function is called by Discord as a user types in the 'event_name' option
    for a slash command. It fetches the current season's schedule from fastf1
    and returns a list of matching event names.

    Args:
        interaction: The Discord interaction object.
        current: The current string the user has typed.

    Returns:
        A list of app_commands.Choice objects for autocomplete.
    """
    choices = []
    try:
        current_year = datetime.datetime.now().year
        # Fetch the event schedule to provide autocomplete choices
        schedule = fastf1.get_event_schedule(current_year, include_testing=False)
        # Create a list of choices from the unique event names in the schedule
        choices = [
            app_commands.Choice(name=event_name, value=event_name)
            for event_name in schedule['EventName'].unique().tolist()
            if current.lower() in event_name.lower() # Filter choices based on user input
        ]
    except Exception as e:
        log.error(f"Error during event autocomplete: {e}", exc_info=True)
    log.debug(f"Event autocomplete for '{current}': Found {len(choices)} choices.")
    return choices

def pace_plot(plot_type, season_idx, event_idx, session_idx, driverList):
    """
    Generates a pace analysis plot for drivers or teams.

    This function fetches lap data from completed sessions of a given F1 event,
    processes it, and creates a box plot overlaid with a swarm plot to visualize
    lap time distributions. The plot can be grouped by driver or by team.

    Args:
        plot_type (str): The type of plot to generate, either 'driver' or 'team'.
        season_idx (int): The year of the season.
        event_idx (str or int): The name or round number of the event.
        session_idx (int): The number of the last completed session to include data from.
        driverList (dict): A dictionary of live driver data from Redis, used for
                           ordering and team color information.

    Returns:
        matplotlib.figure.Figure or None: The generated plot figure, or None if
                                          no data is available.
    """
    # --- Historical Data Loading (FastF1) ---
    # Create a list of all completed FastF1 session objects for the current event.
    session_list = [
        fastf1.get_session(season_idx, event_idx, i)
        for i in range(1, 1 + session_idx)
    ]

    # Load the data for each session. This can be time-consuming.
    # We disable telemetry loading as we only need lap data.
    for session in session_list:
        session.load(telemetry=False, weather=True, messages=True)

    if len(session_list) == 0:
        return None

    # --- Data Aggregation & Cleaning ---
    # Get a list of driver numbers, sorted by their current position on the timing screen.
    # This ensures the plot's x-axis is ordered by the current race/quali standings.
    drivers = [
        key
        for key, _ in sorted(
            driverList.items(), key=lambda item: int(item[1]["Line"])
        )
    ]

    # Create a color palette for tyre compounds.
    tire_palette = msgStyle["compoundRGB"]
    compounds = list(tire_palette.keys())

    # For each session, aggregate all valid laps for the specified drivers.
    # A chain of FastF1 filters is applied to ensure data quality and relevance:
    # - pick_drivers():     Selects laps only for the drivers currently on track.
    # - pick_wo_box():      Excludes in-laps and out-laps (laps entering/leaving pits).
    # - pick_not_deleted(): Excludes laps invalidated by race control (e.g., for track limits).
    # - pick_accurate():    Excludes laps with known timing inaccuracies.
    # - pick_compounds():   Includes only laps set on standard race compounds (W, I, S, M, H).
    # - pick_track_status("1"): Includes only laps set under green flag conditions.
    driver_laps_per_session = [
        session.laps.pick_drivers(drivers)
        .pick_wo_box()
        .pick_not_deleted()
        .pick_accurate()
        .pick_compounds(compounds)
        .pick_track_status("1")
        for session in session_list
    ]
    for idx, session_laps in enumerate(driver_laps_per_session):
        session_laps["Session_Type"] = session_list[idx].session_info['Type']
        session_laps['Session_Number'] = idx
    # Combine the laps from all sessions into a single pandas DataFrame.
    driver_laps = pd.concat(driver_laps_per_session)
    driver_laps = driver_laps.reset_index()

    # --- Plotting Setup ---
    # Determine the order of drivers on the x-axis based on their current timing screen position.
    driver_order = [driverList[i]["Tla"] for i in drivers]
    team_order = list(dict.fromkeys([driverList[i]["TeamName"] for i in drivers]))
    # Create a color palette mapping each driver's TLA to their team color.
    driver_palette = {
        value["Tla"]: f"#{value['TeamColour']}"
        for _, value in driverList.items()
    }
    driver_palette_wet = { key: to_rgba(val, alpha=0.5) for key, val in driver_palette.items() }
    session_type_marker = {
        "Race": "o",
        "Qualifying": 7,
        "Practice": "s",
    }

    # Initialize the matplotlib figure and axes.
    fig, ax = plt.subplots(figsize=(21, 9))
    fig.suptitle(f"{season_idx} {event_idx} {plot_type} pace".title())
    ax.set_xlabel("Driver")
    ax.set_ylabel("Lap Time")
    # ax.grid(axis="y", linestyle="--")
    ax.set_xticks(np.arange(-0.5, 30, 1), minor=True)
    ax.grid(which="major",axis = 'y', linestyle = '--')
    ax.grid(which="minor",axis = 'x', linestyle = '--')
    ax.grid(which="minor",axis = 'y', linestyle = ':', linewidth=0.5)
    ax.yaxis.set_minor_locator(tick.AutoMinorLocator())
    time_formatter = tick.FuncFormatter( lambda x, y: f"{int(x//60)}:{int(x%60):02}")
    ax.yaxis.set_major_formatter(time_formatter)
    ax.legend(
        handles=[
            mlines.Line2D(
                [],
                [],
                marker=marker,
                label=label,
                linestyle="None",
                markersize=10,
                color="white",
            )
            for label, marker in session_type_marker.items()
        ]
    )
    fig.tight_layout()

    # Convert the 'LapTime' (a timedelta object) to total seconds for plotting on a numeric axis.
    driver_laps["LapTime(s)"] = driver_laps["LapTime"].dt.total_seconds()
    # Calculate a threshold to filter out unrealistically slow laps (e.g., cool-down laps),
    # but preserve all race laps to show the full pace distribution during the race.
    # The threshold is the smaller of 120% of the fastest lap or the fastest lap + 20 seconds.
    threshold = min(
        [driver_laps["LapTime(s)"].min() * 1.2, driver_laps["LapTime(s)"].min() + 20.0]
    )
    driver_laps = driver_laps[
        (driver_laps["LapTime(s)"] <= threshold)
        | (driver_laps["Session_Type"] == "Race")
    ]

    used_compounds = sorted(
        driver_laps["Compound"].unique(),
        key=lambda x: compounds.index(x)
    )

    if plot_type == 'driver':
        # 1. Create the box plot to show the distribution of lap times for each driver.
        #    This gives a good overview of each driver's pace consistency.
        # Dry Tires
        sns.boxplot(
            data=driver_laps[ driver_laps['Compound'].isin(['SOFT', 'MEDIUM', 'HARD']) ],
            x="Driver",
            y="LapTime(s)",
            hue="Driver",
            order=driver_order,
            palette=driver_palette,
            fill=False,
            showfliers=False,
            legend=False,
            saturation=1,
            ax=ax,
        )

        # Wet Tires
        sns.boxplot(
            data=driver_laps[ driver_laps['Compound'].isin(['WET', 'INTERMEDIATE']) ],
            x="Driver",
            y="LapTime(s)",
            hue="Driver",
            order=driver_order,
            palette=driver_palette_wet,
            fill=False,
            showfliers=False,
            legend=False,
            ax=ax,
        )

        # 2. Overlay a swarm plot to show each individual valid lap.
        #    Each point is colored by the tyre compound used for that lap, providing
        #    deeper insight into the pace on different compounds.
        for session_no in range(session_idx):
            session_type = session_list[session_no].session_info['Type']
            marker = session_type_marker[session_type]
            tire_palette_adj = { key: to_rgba(val, alpha=(session_no + 1.)/session_idx) for key, val in tire_palette.items() }
            sns.swarmplot(
                data=driver_laps[ driver_laps['Session_Number'] == session_no ],
                x="Driver",
                y="LapTime(s)",
                order=driver_order,
                hue="Compound",
                palette=tire_palette_adj,
                hue_order=used_compounds,
                linewidth=0,
                size=5,
                marker=marker,
                dodge=True,
                legend=False,
                ax=ax,
            )
    elif plot_type == 'team':
        # --- Plotting ---
        # 1. Create the box plot to show the distribution of lap times for each team.
        #    This gives a good overview of each team's pace consistency.
        # Dry Tires
        sns.boxplot(
            data=driver_laps,
            x="Team",
            y="LapTime(s)",
            hue="Compound",
            order=team_order,
            palette=tire_palette,
            hue_order=used_compounds,
            fill=False,
            showfliers=False,
            legend=False,
            gap=0.1,
            ax=ax,
        )

        # 2. Overlay a swarm plot to show each individual valid lap.
        #    Each point is colored by the tyre compound used for that lap, providing
        #    deeper insight into the pace on different compounds.
        for session_no in range(session_idx):
            session_type = session_list[session_no].session_info['Type']
            marker = session_type_marker[session_type]
            tire_palette_adj = { key: to_rgba(val, alpha=(session_no + 1.)/session_idx) for key, val in tire_palette.items() }
            sns.swarmplot(
                data=driver_laps[ driver_laps['Session_Number'] == session_no ],
                x="Team",
                y="LapTime(s)",
                order=team_order,
                hue="Compound",
                palette=tire_palette_adj,
                hue_order=used_compounds,
                linewidth=0,
                size=5,
                marker=marker,
                dodge=True,
                legend=False,
                ax=ax,
            )
    return fig

class StrategistGroup(app_commands.Group):
    """A Discord slash command group for all strategist-related commands."""

    def __init__(self):
        # Initialize the command group with a name and description.
        super().__init__(name="strategist", description="Commands for the Strategist.")
        log.info("Strategist command group initialized.")
        # Locks to prevent multiple concurrent plot generation requests for the same plot type,
        # which can be resource-intensive.
        self.team_pace_lock=asyncio.Lock()
        self.driver_pace_lock=asyncio.Lock()

    @app_commands.command(
        name="schedule",
        description="Get the F1 schedule for an event, or the next upcoming event.",
    )
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def schedule(
        self, interaction: discord.Interaction, event_name: Optional[str] = None
    ):
        """
        Fetches and displays the F1 schedule for a given event.

        If an event name is provided, it shows the schedule for that specific event.
        If no event name is provided, it displays the schedule for the next upcoming event
        in the current season.

        Args:
            interaction: The Discord interaction object.
            event_name: The name of the F1 event (optional).
        """
        log.info(
            f"Command '/strategist schedule' invoked by {interaction.user} (Event: {event_name or 'Next Upcoming'})"
        )
        await interaction.response.defer(ephemeral=True, thinking=True)

        target_event = None
        current_year = datetime.datetime.now().year
        error_message = None

        try:
            if event_name:
                # User specified an event name
                log.info(f"Fetching schedule for specified event: {event_name}")
                target_event = fastf1.get_event(current_year, event_name)
            else:
                # No event name specified, find the next upcoming event
                log.info("No specific event provided, finding next upcoming event.")
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                remaining_events = fastf1.get_events_remaining(include_testing=False)
                if not remaining_events.empty:
                    target_event = remaining_events.iloc[0]
                    log.info(f"Found next upcoming event: {target_event['EventName']}")
                else:
                    log.warning(
                        f"No upcoming races found for the {current_year} season after {now_utc}."
                    )
                    error_message = f"ℹ️ Couldn't find any upcoming F1 races scheduled for the rest of {current_year}."

            # --- Send response ---
            if target_event is not None and not target_event.empty:
                # Create an embed for the schedule
                embed = discord.Embed(
                    title=f"📅 F1 Event: {target_event['EventName']} (Round {target_event['RoundNumber']})",
                    description=f"📍 Location: {target_event['Location']}, {target_event['Country']}",
                    color=discord.Color.blurple(),
                )

                # Find all valid sessions first
                sessions = []
                for i in range(1, 6):
                    session_name = target_event.get(f"Session{i}")
                    session_date = target_event.get(f"Session{i}Date")
                    if session_name and pd.notna(session_date):
                        sessions.append({"name": session_name, "date": session_date})

                # Add each session as a separate field in the embed
                if sessions:
                    for idx, session in enumerate(sessions):
                        unix_ts = int(session["date"].timestamp())
                        timestamp_str = (
                            f"<t:{unix_ts}:d> <t:{unix_ts}:t> (<t:{unix_ts}:R>)"
                        )

                        # Bold the name of the last session (usually the Race)
                        is_last_session = idx == len(sessions) - 1
                        field_name = (
                            f"**{session['name']}**"
                            if is_last_session
                            else session["name"]
                        )
                        embed.add_field(
                            name=field_name, value=timestamp_str, inline=False
                        )

                embed.set_footer(
                    text="Note: Displayed in your local time. Session names might differ for Sprint weekends."
                )
                log.info(
                    f"Sending schedule for {target_event['EventName']} to {interaction.user}"
                )
                await interaction.followup.send(embed=embed)
            elif error_message:
                await interaction.followup.send(error_message)
            else:
                log.error(
                    f"Could not find event '{event_name}' or any upcoming events."
                )
                await interaction.followup.send(
                    f"❌ Could not find the event named '{event_name}'. Please check the name and try again."
                )
        except Exception as e:
            log.error(f"Error executing '/strategist schedule': {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred while fetching the F1 schedule."
            )

    @app_commands.command(
        name="trackmap",
        description="Displays the track map for an event, or the next upcoming event.",
    )
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def trackmap(
        self, interaction: discord.Interaction, event_name: Optional[str] = None
    ):
        """
        Displays the track map for a given F1 event.

        If an event name is provided, it shows the track map for that event.
        If no event name is provided, it displays the map for the next upcoming event.
        The track map images are stored locally.

        Args:
            interaction: The Discord interaction object.
            event_name: The name of the F1 event (optional).
        """
        log.info(
            f"Command '/strategist trackmap' invoked by {interaction.user} for event: {event_name}"
        )
        await interaction.response.defer(ephemeral=True, thinking=True)

        file_path = None
        current_year = datetime.datetime.now().year
        error_message = None

        try:
            if event_name:
                # User specified an event name
                log.info(f"Fetching event data for: {event_name}")
                target_event = fastf1.get_event(current_year, event_name)
            else:
                # No event name specified, find the next upcoming event
                log.info("No specific event provided, finding next upcoming event.")
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                remaining_events = fastf1.get_events_remaining(include_testing=False)
                if not remaining_events.empty:
                    target_event = remaining_events.iloc[0]
                    log.info(f"Found next upcoming event: {target_event['EventName']}")
                else:
                    log.warning(
                        f"No upcoming races found for the {current_year} season after {now_utc}."
                    )
                    error_message = f"ℹ️ Couldn't find any upcoming F1 races scheduled for the rest of {current_year}."

            if target_event.empty:
                error_message = (
                    f"❌ Could not find event '{event_name}'. Please check the name."
                )
            else:
                track_location = target_event["Location"]
                file_path = os.path.join(TRACKS_DIR, f"{track_location}.png")
                log.debug(f"Constructed track map path: {file_path}")

                if not os.path.exists(file_path):
                    log.warning(f"Track map file not found at: {file_path}")
                    error_message = f"❌ Sorry, the track map for '{track_location}' is not available."
                    file_path = None  # Prevent attempt to send

        except Exception as e:
            log.error(
                f"Unexpected error in '/strategist trackmap' setup: {e}", exc_info=True
            )
            error_message = (
                "❌ An unexpected error occurred while preparing the track map."
            )
            file_path = None

        # --- Attempt to Send File or Error ---
        if file_path and not error_message:
            try:
                discord_file = discord.File(file_path)
                log.info(f"Sending track map '{file_path}' to {interaction.user}")
                await interaction.followup.send(file=discord_file)
            except Exception as e:
                log.error(
                    f"Error sending track map file '{file_path}': {e}", exc_info=True
                )
                await interaction.followup.send(
                    "❌ An error occurred while sending the track map image."
                )
        elif error_message:
            await interaction.followup.send(error_message)

    @app_commands.command(
        name="driver_pace",
        description="Generates a box plot of lap times for each driver from all completed sessions of the current event.",
    )
    async def driver_pace(self, interaction: discord.Interaction):
        """
        Generates and sends a box plot of driver pace for the current event.

        The plot shows the distribution of valid lap times for each driver across all
        completed sessions of the current race weekend. Individual laps are plotted
        as points, colored by the tyre compound used. The plot is cached in Redis
        to reduce regeneration time.

        Args:
            interaction: The Discord interaction object.
        """
        log.info(f"Command '/strategist driver_pace' invoked by {interaction.user}")
        await interaction.response.defer(ephemeral=True, thinking=True)
        # --- Live Data Fetching for Context ---
        # This command analyzes historical data, but it needs live context to know *which*
        # event to look at and which sessions have been completed.
        # - DriverList: Used to order drivers on the plot by their current standing.
        # - SessionInfo: Used to identify the current year, event, and session name.
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
        )
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")

        # --- Session Identification for FastF1 ---
        # Map the live session names (e.g., "Practice 1") to the session numbers
        # that the FastF1 library uses (e.g., 1, 2, 3, 4, 5).
        session_number_mapping = {
            "Practice 1": 1,
            "Practice 2": 2,
            "Practice 3": 3,
            "Day 1": 1,
            "Day 2": 2,
            "Day 3": 3,
            "Sprint Qualifying": 2,
            "Sprint": 3,
            "Qualifying": 4,
            "Race": 5,
        }
        # Determine the parameters for fetching historical data. This identifies the
        # year, event number, and the latest *completed* session. If the current
        # session is still live ('Complete' != status), we subtract 1 to ensure
        # we only plot data from fully completed sessions.
        session_idx = {
            "year": int(
                datetime.datetime.strptime(
                    sessionInfo["StartDate"], "%Y-%m-%dT%H:%M:%S"
                ).year
            ),
            "event": sessionInfo["Meeting"]["Name"],
            "session": int(session_number_mapping[sessionInfo["Name"]])
            - int("Complete" != sessionInfo["ArchiveStatus"]["Status"]),
        }
        plot_name = f"driver-pace-{session_idx['year']}-{session_idx['event']}-{session_idx['session']}.png"
        # --- Caching & Plot Generation ---
        # The plot is cached in Redis to avoid regenerating it on every request.
        # A lock is used to prevent race conditions from multiple simultaneous requests.
        try:
            bio = None
            # First, check if the plot is already in the cache.
            if cached_bytes := await redis_client.get(plot_name):
                bio = io.BytesIO(cached_bytes)
            # If not cached, acquire a lock and re-check the cache (double-checked locking).
            elif await self.driver_pace_lock.acquire() and (cached_bytes := await redis_client.get(plot_name)):
                bio = io.BytesIO(cached_bytes)
            # If still not cached, generate the plot.
            elif fig := await asyncio.to_thread(pace_plot, 'driver', session_idx['year'], session_idx['event'], session_idx['session'], driverList):
                bio = io.BytesIO()
                fig.savefig(bio, dpi=600, format="png")
                bio.seek(0)
                # Save the newly generated plot to the cache with a 1-day expiry.
                await redis_client.set(
                    plot_name,
                    bio.getvalue(),
                    ex=86400, # 1 day
                )
        finally:
            # Ensure the lock is always released.
            if self.driver_pace_lock.locked():
                self.driver_pace_lock.release()
            # --- Send Response ---
            # Create a discord.File object from the stream.
            if bio != None:
                attachment = discord.File(
                    bio,
                    filename=plot_name,
                )
                # Send the file as a response to the interaction.
                await interaction.followup.send(file=attachment)
                return
            else:
                # Handle cases where no data is available for plotting.
                await interaction.followup.send(
                        content="No completed sessions available to generate a pace plot."
                    )
                return

    @app_commands.command(
        name="team_pace",
        description="Generates a box plot of lap times for each team from all completed sessions of the current event.",
    )
    async def team_pace(self, interaction: discord.Interaction):
        """
        Generates and sends a box plot of team pace for the current event.

        The plot shows the distribution of valid lap times for each team across all
        completed sessions of the current race weekend. Individual laps are plotted
        as points, colored by the tyre compound used. The plot is cached in Redis
        to reduce regeneration time.

        Args:
            interaction: The Discord interaction object.
        """
        log.info(f"Command '/strategist team_pace' invoked by {interaction.user}")
        await interaction.response.defer(ephemeral=True, thinking=True)
        # --- Live Data Fetching for Context ---
        # This command analyzes historical data, but it needs live context to know *which*
        # event to look at and which sessions have been completed.
        # - DriverList: Used to order drivers on the plot by their current standing.
        # - SessionInfo: Used to identify the current year, event, and session name.
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
        )
        driverList = await redis_client.json().get("DriverList")
        sessionInfo = await redis_client.json().get("SessionInfo")

        # --- Session Identification for FastF1 ---
        # Map the live session names (e.g., "Practice 1") to the session numbers
        # that the FastF1 library uses (e.g., 1, 2, 3, 4, 5).
        session_number_mapping = {
            "Practice 1": 1,
            "Practice 2": 2,
            "Practice 3": 3,
            "Day 1": 1,
            "Day 2": 2,
            "Day 3": 3,
            "Sprint Qualifying": 2,
            "Sprint": 3,
            "Qualifying": 4,
            "Race": 5,
        }
        # Determine the parameters for fetching historical data. This identifies the
        # year, event number, and the latest *completed* session. If the current
        # session is still live ('Complete' != status), we subtract 1 to ensure
        # we only plot data from fully completed sessions.
        session_idx = {
            "year": int(
                datetime.datetime.strptime(
                    sessionInfo["StartDate"], "%Y-%m-%dT%H:%M:%S"
                ).year
            ),
            "event": sessionInfo["Meeting"]["Name"],
            "session": int(session_number_mapping[sessionInfo["Name"]])
            - int("Complete" != sessionInfo["ArchiveStatus"]["Status"]),
        }
        plot_name = f"team-pace-{session_idx['year']}-{session_idx['event']}-{session_idx['session']}.png"
        # --- Caching & Plot Generation ---
        # The plot is cached in Redis to avoid regenerating it on every request.
        # A lock is used to prevent race conditions from multiple simultaneous requests.
        try:
            bio = None
            # First, check if the plot is already in the cache.
            if cached_bytes := await redis_client.get(plot_name):
                bio = io.BytesIO(cached_bytes)
            # If not cached, acquire a lock and re-check the cache (double-checked locking).
            elif await self.team_pace_lock.acquire() and (cached_bytes := await redis_client.get(plot_name)):
                bio = io.BytesIO(cached_bytes)
            # If still not cached, generate the plot.
            elif fig := await asyncio.to_thread(pace_plot, 'team', session_idx['year'], session_idx['event'], session_idx['session'], driverList):
                bio = io.BytesIO()
                fig.savefig(bio, dpi=600, format="png")
                bio.seek(0)
                # Save the newly generated plot to the cache with a 1-day expiry.
                await redis_client.set(
                    plot_name,
                    bio.getvalue(),
                    ex=86400, # 1 day
                )
        finally:
            # Ensure the lock is always released.
            if self.team_pace_lock.locked():
                self.team_pace_lock.release()
            # --- Send Response ---
            # Create a discord.File object from the stream.
            if bio != None:
                attachment = discord.File(
                    bio,
                    filename=plot_name,
                )
                # Send the file as a response to the interaction.
                await interaction.followup.send(file=attachment)
                return
            else:
                # Handle cases where no data is available for plotting.
                await interaction.followup.send(
                        content="No completed sessions available to generate a pace plot."
                    )
                return
                
        
    @app_commands.command(
        name="driver_standing", description="View the current World Driver Championship standings."
    )
    async def driver_standing(self, interaction: discord.Interaction):
        """
        Displays the current World Driver Championship standings.

        It fetches the latest standings from the Ergast API and calculates which
        drivers are still mathematically in contention for the championship based
        on the points remaining in the season.

        Args:
            interaction: The Discord interaction object.
        """
        # Get current driver standings from the Ergast API
        driver_standings = (
            Ergast()
            .get_driver_standings(
                season=datetime.datetime.now(datetime.timezone.utc).year
            )
            .content[0]
        )

        # Define points awarded for different race formats
        POINTS_FOR_CONVENTIONAL = 25  # Winning a conventional race
        POINTS_FOR_SPRINT = (
            8 + 25
        )  # Winning a sprint race (includes sprint race win and Sunday race win)

        # Get remaining events in the current season
        events = fastf1.events.get_events_remaining(include_testing=True)

        # Calculate total possible points from remaining events based on their format
        sprint_points = (
            len(events.loc[events["EventFormat"] == "sprint_qualifying"])
            * POINTS_FOR_SPRINT
        )
        conventional_points = (
            len(events.loc[events["EventFormat"] == "conventional"])
            * POINTS_FOR_CONVENTIONAL
        )
        total_points_remaining = (
            sprint_points + conventional_points
        )  # Maximum points a driver can still earn

        # Determine the points of the current leader
        LEADER_POINTS = int(driver_standings.loc[0]["points"])

        # Filter drivers into those still mathematically in contention for the championship and those out of contention
        driver_in_contention = driver_standings[
            driver_standings["points"] >= LEADER_POINTS - total_points_remaining
        ]
        driver_outof_contention = driver_standings[
            driver_standings["points"] < LEADER_POINTS - total_points_remaining
        ]

        # Create a Discord embed for drivers still in contention
        embed_in_contention = discord.Embed(
            title="World Driver Champion", color=discord.Color.gold()
        )
        for _, driver in driver_in_contention.iterrows():
            embed_in_contention.add_field(
                name=f"{driver['givenName']} {driver['familyName']}",
                value=f"`{driver['points']}`",
                inline=False,
            )

        # If there are drivers out of contention, create a separate embed for them
        if not driver_outof_contention.empty:
            embed_outof_contention = discord.Embed(title="Out of Contention")
            for _, driver in driver_outof_contention.iterrows():
                embed_outof_contention.add_field(
                    name=f"{driver['givenName']} {driver['familyName']}",
                    value=f"`{driver['points']}`",
                    inline=False,
                )
            await interaction.response.send_message(
                embeds=[embed_in_contention, embed_outof_contention], ephemeral=True
            )
        else:
            # If all drivers are still in contention, send only the first embed
            await interaction.response.send_message(
                embeds=[embed_in_contention], ephemeral=True
            )

    @app_commands.command(
        name="team_standing", description="View the current World Constructor Championship standings."
    )
    async def team_standing(self, interaction: discord.Interaction):
        """
        Displays the current World Constructor Championship standings.

        It fetches the latest standings from the Ergast API and calculates which
        constructors are still mathematically in contention for the championship
        based on the points remaining in the season.

        Args:
            interaction: The Discord interaction object.
        """
        # Get current constructor standings from the Ergast API
        constructor_standings = (
            Ergast()
            .get_constructor_standings(
                season=datetime.datetime.now(datetime.timezone.utc).year
            )
            .content[0]
        )

        # Define points awarded for different race formats, considering both drivers' potential scores
        POINTS_FOR_CONVENTIONAL = 25 + 18  # Top two positions in a conventional race
        POINTS_FOR_SPRINT = (
            8 + 7 + POINTS_FOR_CONVENTIONAL
        )  # Points from sprint (for top 8) plus top two in the main race

        # Get remaining events in the current season
        events = fastf1.events.get_events_remaining(include_testing=True)

        # Calculate total possible points from remaining events based on their format
        sprint_points = (
            len(events.loc[events["EventFormat"] == "sprint_qualifying"])
            * POINTS_FOR_SPRINT
        )
        conventional_points = (
            len(events.loc[events["EventFormat"] == "conventional"])
            * POINTS_FOR_CONVENTIONAL
        )
        total_points_remaining = (
            sprint_points + conventional_points
        )  # Maximum points a constructor can still earn

        # Determine the points of the current leader
        LEADER_POINTS = int(constructor_standings.loc[0]["points"])

        # Filter constructors into those still mathematically in contention and those out of contention
        constructor_in_contention = constructor_standings[
            constructor_standings["points"] >= LEADER_POINTS - total_points_remaining
        ]
        constructor_outof_contention = constructor_standings[
            constructor_standings["points"] < LEADER_POINTS - total_points_remaining
        ]

        # Create a Discord embed for constructors still in contention
        embed_in_contention = discord.Embed(
            title="World Constructor Champion", color=discord.Color.gold()
        )
        for _, constructor in constructor_in_contention.iterrows():
            embed_in_contention.add_field(
                name=f"{constructor['constructorName']}",
                value=f"`{constructor['points']}`",
                inline=False,
            )

        # If there are constructors out of contention, create a separate embed
        if not constructor_outof_contention.empty:
            embed_outof_contention = discord.Embed(title="Out of Contention")
            for _, constructor in constructor_outof_contention.iterrows():
                embed_outof_contention.add_field(
                    name=f"{constructor['constructorName']}",
                    value=f"`{constructor['points']}`",
                    inline=False,
                )
            await interaction.response.send_message(
                embeds=[embed_in_contention, embed_outof_contention], ephemeral=True
            )
        else:
            # If all constructors are still in contention, send only the first embed
            await interaction.response.send_message(
                embeds=[embed_in_contention], ephemeral=True
            )
