# strategist_group.py

# Standard library imports
import datetime
import io
import logging
import os
from typing import Optional

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
    """
    Provides autocomplete suggestions for F1 event names in the current season.
    This function is called by Discord as the user types in a command option.
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

def pace_plot(plot_type, season, event, session, driverList):
    # --- Historical Data Loading (FastF1) ---
    # Create a list of all completed FastF1 session objects for the current event.
    session_list = [
        fastf1.get_session(season, event, i)
        for i in range(1, 1 + session)
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
        "Qualifying": "s",
        "Practice": "X",
    }

    # Initialize the matplotlib figure and axes.
    fig, ax = plt.subplots(figsize=(21, 9))
    fig.suptitle(f"{season} {event} {plot_type} pace".title())
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
    fig.tight_layout()

    # Convert the 'LapTime' (a timedelta object) to total seconds for plotting on a numeric axis.
    driver_laps["LapTime(s)"] = driver_laps["LapTime"].dt.total_seconds()
    driver_laps = driver_laps[
        (driver_laps["LapTime(s)"] <= driver_laps["LapTime(s)"].min() * 1.25)
        | (driver_laps["Session_Type"] == "Race")
    ]

    used_compounds = sorted(
        driver_laps["Compound"].unique(),
        key=lambda x: compounds.index(x)
    )

    if plot_type == 'driver':
        # 1. Create the violin plot to show the distribution of lap times for each driver.
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
            # saturation=0.1,
        )

        # 2. Overlay a swarm plot to show each individual valid lap.
        #    Each point is colored by the tyre compound used for that lap, providing
        #    deeper insight into the pace on different compounds.
        for session_type, marker in session_type_marker.items():
            sns.swarmplot(
                data=driver_laps[ driver_laps['Session_Type'] == session_type ],
                x="Driver",
                y="LapTime(s)",
                order=driver_order,
                hue="Compound",
                palette=tire_palette,
                hue_order=used_compounds,
                linewidth=0,
                size=5,
                marker=marker,
                dodge=True,
                legend=False,
            )
    elif plot_type == 'team':
        # # --- Plotting ---
        # 1. Create the violin plot to show the distribution of lap times for each driver.
        #    This gives a good overview of each driver's pace consistency.
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
        )

        # 2. Overlay a swarm plot to show each individual valid lap.
        #    Each point is colored by the tyre compound used for that lap, providing
        #    deeper insight into the pace on different compounds.
        for session_type, marker in session_type_marker.items():
            sns.swarmplot(
                data=driver_laps[ driver_laps['Session_Type'] == session_type ],
                x="Team",
                y="LapTime(s)",
                order=team_order,
                hue="Compound",
                palette=tire_palette,
                hue_order=used_compounds,
                linewidth=0,
                size=5,
                marker=marker,
                dodge=True,
                legend=False,
            )
    return fig

class StrategistGroup(app_commands.Group):
    """
    Encapsulates commands related to Race Strategy.
    This class defines a slash command group for Discord.
    """

    def __init__(self):
        # Initialize the command group with a name and description
        super().__init__(name="strategist", description="Commands for the Strategist.")
        log.info("Strategist command group initialized.")

    @app_commands.command(
        name="schedule",
        description="Get the F1 schedule for an event, or the next upcoming event.",
    )
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def schedule(
        self, interaction: discord.Interaction, event_name: Optional[str] = None
    ):
        """Fetches and displays F1 schedule: specific event if name provided, otherwise the next one."""
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
        """Sends the specified track map image ephemerally."""
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
        Generates and sends a box plot illustrating the pace distribution
        of each driver across all completed sessions of the current event.
        Each point on the plot represents a valid lap, colored by the tyre
        compound used.
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

        # --- Caching ---
        # The plot is cached in Redis to avoid regenerating it on every request.
        # The cache key includes the year, event, and session to ensure it's unique.
        # The cache expires after 12 hours (43200 seconds).
        bio = io.BytesIO()
        cached_bytes = await redis_client.get(
            f"driver-pace-{session_idx['year']}-{session_idx['event']}-{session_idx['session']}.png"
        )
        if cached_bytes:
            bio = io.BytesIO(cached_bytes)
        else:

            fig = pace_plot('driver', session_idx['year'], session_idx['event'], session_idx['session'], driverList)
            if fig is None:
                await interaction.followup.send(
                    content="No completed sessions available to generate a pace plot."
                )
                return

            # --- Image Generation & Caching ---
            # Save the generated plot to an in-memory binary stream (BytesIO).
            fig.savefig(bio, dpi=600, format="png")
            # Reset the stream's position to the beginning before reading.
            bio.seek(0)
            # Cache the newly generated plot in Redis.
            await redis_client.set(
                f"driver-pace-{session_idx['year']}-{session_idx['event']}-{session_idx['session']}.png",
                bio.getvalue(),
                ex=43200,
            )

        # --- Send Response ---
        # Create a discord.File object from the stream.
        attachment = discord.File(
            bio,
            filename=f"driver-pace-{session_idx['year']}-{session_idx['event']}-{session_idx['session']}.png",
        )
        # Send the file as a response to the interaction.
        await interaction.followup.send(file=attachment)
        return

    @app_commands.command(
        name="team_pace",
        description="Generates a box plot of lap times for each team from all completed sessions of the current event.",
    )
    async def team_pace(self, interaction: discord.Interaction):
        """
        Generates and sends a box plot illustrating the pace distribution
        of each team across all completed sessions of the current event.
        Each point on the plot represents a valid lap, colored by the tyre
        compound used.
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

        # --- Caching ---
        # The plot is cached in Redis to avoid regenerating it on every request.
        # The cache key includes the year, event, and session to ensure it's unique.
        # The cache expires after 12 hours (43200 seconds).
        bio = io.BytesIO()
        cached_bytes = await redis_client.get(
            f"team-pace-{session_idx['year']}-{session_idx['event']}-{session_idx['session']}.png"
        )
        if cached_bytes:
            bio = io.BytesIO(cached_bytes)
        else:
            
            fig = pace_plot('team', session_idx['year'], session_idx['event'], session_idx['session'], driverList)
            
            if fig is None:
                await interaction.followup.send(
                    content="No completed sessions available to generate a pace plot."
                )
                return
            
            # --- Image Generation & Caching ---
            # Save the generated plot to an in-memory binary stream (BytesIO).
            fig.savefig(bio, dpi=600, format="png")
            # Reset the stream's position to the beginning before reading.
            bio.seek(0)
            # Cache the newly generated plot in Redis.
            await redis_client.set(
                f"team-pace-{session_idx['year']}-{session_idx['event']}-{session_idx['session']}.png",
                bio.getvalue(),
                ex=43200,
            )

        # --- Send Response ---
        # Create a discord.File object from the stream.
        attachment = discord.File(
            bio,
            filename=f"team-pace-{session_idx['year']}-{session_idx['event']}-{session_idx['session']}.png",
        )
        # Send the file as a response to the interaction.
        await interaction.followup.send(file=attachment)
        return

    @app_commands.command(
        name="driver_standing", description="World Driver Champion standing"
    )
    async def driver_standing(self, interaction: discord.Interaction):
        """
        Displays the World Driver Championship standings for the current year,
        highlighting drivers still in contention based on remaining points.
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
            len(events.loc[events["EventFormat"] == "sprint_shootout"])
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
        name="team_standing", description="World Constructor Champion standing"
    )
    async def team_standing(self, interaction: discord.Interaction):
        """
        Displays the World Constructor Championship standings for the current year,
        highlighting constructors still in contention based on remaining points.
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
            len(events.loc[events["EventFormat"] == "sprint_shootout"])
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
