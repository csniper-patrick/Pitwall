# strategist_group.py

import discord
from discord import app_commands
import os
import fastf1
import datetime
import logging
import pandas as pd
from dotenv import load_dotenv
from typing import Optional
import matplotlib.pyplot as plt
import matplotlib.style as style
import fastf1.plotting
from labellines import labelLines
import datetime
import seaborn as sns
import io
import redis.asyncio as redis

# Get a logger instance for this module
log = logging.getLogger(__name__)

from utils import *
load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

fastf1.plotting.setup_mpl(color_scheme='fastf1')

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


class StrategistGroup(app_commands.Group):
    """
    Encapsulates commands related to Race Strategy.
    This class defines a slash command group for Discord.
    """
    def __init__(self):
        # Initialize the command group with a name and description
        super().__init__(name="strategist", description="Commands for the Strategist.")
        log.info("Strategist command group initialized.")

    @app_commands.command(name="schedule", description="Get the F1 schedule for an event, or the next upcoming event.")
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def schedule(self, interaction: discord.Interaction, event_name: Optional[str] = None):
        """Fetches and displays F1 schedule: specific event if name provided, otherwise the next one."""
        log.info(f"Command '/strategist schedule' invoked by {interaction.user} (Event: {event_name or 'Next Upcoming'})")
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
                    log.warning(f"No upcoming races found for the {current_year} season after {now_utc}.")
                    error_message = f"ℹ️ Couldn't find any upcoming F1 races scheduled for the rest of {current_year}."

            # --- Send response ---
            if target_event is not None and not target_event.empty:
                # Create an embed for the schedule
                embed = discord.Embed(
                    title=f"📅 F1 Event: {target_event['EventName']} (Round {target_event['RoundNumber']})",
                    description=f"📍 Location: {target_event['Location']}, {target_event['Country']}",
                    color=discord.Color.blurple()
                )

                # Find all valid sessions first
                sessions = []
                for i in range(1, 6):
                    session_name = target_event.get(f'Session{i}')
                    session_date = target_event.get(f'Session{i}Date')
                    if session_name and pd.notna(session_date):
                        sessions.append({'name': session_name, 'date': session_date})

                # Add each session as a separate field in the embed
                if sessions:
                    for idx, session in enumerate(sessions):
                        unix_ts = int(session['date'].timestamp())
                        timestamp_str = f"<t:{unix_ts}:d> <t:{unix_ts}:t> (<t:{unix_ts}:R>)"

                        # Bold the name of the last session (usually the Race)
                        is_last_session = (idx == len(sessions) - 1)
                        field_name = f"**{session['name']}**" if is_last_session else session['name']
                        embed.add_field(name=field_name, value=timestamp_str, inline=False)

                embed.set_footer(text="Note: Displayed in your local time. Session names might differ for Sprint weekends.")
                log.info(f"Sending schedule for {target_event['EventName']} to {interaction.user}")
                await interaction.followup.send(embed=embed)
            elif error_message:
                await interaction.followup.send(error_message)
            else:
                 log.error(f"Could not find event '{event_name}' or any upcoming events.")
                 await interaction.followup.send(f"❌ Could not find the event named '{event_name}'. Please check the name and try again.")
        except Exception as e:
            log.error(f"Error executing '/strategist schedule': {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred while fetching the F1 schedule.")

    @app_commands.command(name="trackmap", description="Displays the track map for an event, or the next upcoming event.")
    @app_commands.autocomplete(event_name=event_autocomplete)
    async def trackmap(self, interaction: discord.Interaction, event_name: Optional[str] = None):
        """Sends the specified track map image ephemerally."""
        log.info(f"Command '/strategist trackmap' invoked by {interaction.user} for event: {event_name}")
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
                    log.warning(f"No upcoming races found for the {current_year} season after {now_utc}.")
                    error_message = f"ℹ️ Couldn't find any upcoming F1 races scheduled for the rest of {current_year}."
            
            if target_event.empty:
                 error_message = f"❌ Could not find event '{event_name}'. Please check the name."
            else:
                track_location = target_event['Location']
                file_path = os.path.join(TRACKS_DIR, f"{track_location}.png")
                log.debug(f"Constructed track map path: {file_path}")

                if not os.path.exists(file_path):
                    log.warning(f"Track map file not found at: {file_path}")
                    error_message = f"❌ Sorry, the track map for '{track_location}' is not available."
                    file_path = None # Prevent attempt to send

        except Exception as e:
            log.error(f"Unexpected error in '/strategist trackmap' setup: {e}", exc_info=True)
            error_message = "❌ An unexpected error occurred while preparing the track map."
            file_path = None

        # --- Attempt to Send File or Error ---
        if file_path and not error_message:
            try:
                discord_file = discord.File(file_path)
                log.info(f"Sending track map '{file_path}' to {interaction.user}")
                await interaction.followup.send(file=discord_file)
            except Exception as e:
                log.error(f"Error sending track map file '{file_path}': {e}", exc_info=True)
                await interaction.followup.send("❌ An error occurred while sending the track map image.")
        elif error_message:
            await interaction.followup.send(error_message)

    @app_commands.command(name="pace", description="Generates a violin plot of lap times from all completed sessions for the current event.")
    async def pace(self, interaction: discord.Interaction):
        """
        Generates and sends a violin plot illustrating the pace distribution
        of each driver across all completed sessions of the current event.
        Each point on the plot represents a valid lap, colored by the tyre
        compound used.
        """
        log.info(f"Command '/strategist pace' invoked by {interaction.user}")
        await interaction.response.defer(ephemeral=True, thinking=True)
        # --- Live Data Fetching ---
        # Connect to Redis to get information about the *current* live session.
        # This is used to identify the year, event, and which sessions have been completed.
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
        driverList = await redis_client.json().get("DriverList")
        driverList.pop("_kf", None)
        sessionInfo = await redis_client.json().get("SessionInfo")
        sessionInfo.pop("_kf", None)

        # --- Historical Session Identification ---
        # Map F1 session names to the corresponding session number used by FastF1.
        # This allows us to dynamically load the correct historical data.
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
            "Race": 5

        }
        # Determine the parameters for fetching historical data from FastF1.
        # It figures out the year, event number, and the latest completed session.
        # If the current session is not yet 'Complete', it subtracts 1 to only plot completed sessions.
        session_idx ={
            'year': datetime.datetime.strptime(sessionInfo['StartDate'], '%Y-%m-%dT%H:%M:%S').year,
            'event': sessionInfo['Meeting']['Number'],
            'session': session_number_mapping[sessionInfo['Name']] - int( "Complete" != sessionInfo['ArchiveStatus']['Status'] )
        }
        
        # --- Historical Data Loading ---
        # Create a list of all completed FastF1 session objects for the current event.
        session_list = [
            fastf1.get_session(session_idx['year'], session_idx['event'], i)
            for i in range(1, 1 + session_idx['session'])
        ]

        # Load the data for each session. This can be time-consuming.
        for session in session_list:
            session.load(laps=True, telemetry=False, weather=False, messages=False)

        if len(session_list) == 0:
            await interaction.followup.send(content="No completed sessions available to generate a pace plot.")
            return

        # --- Data Aggregation & Cleaning ---
        # Get a list of driver numbers, sorted by their current position on the timing screen.
        drivers = [ key for key, _ in sorted( driverList.items(), key=lambda item: item[1]['Line'] )]

        # For each session, get all valid laps for the specified drivers.
        # - pick_not_deleted(): Excludes laps invalidated by race control.
        # - pick_wo_box(): Excludes in-laps and out-laps.
        # - pick_accurate(): Excludes laps with inaccurate timing data.
        driver_laps_per_session = [
            session.laps.pick_drivers(drivers)
            .pick_not_deleted()
            .pick_wo_box()
            .pick_accurate()
            for session in session_list
        ]
        # Combine the laps from all sessions into a single pandas DataFrame.
        driver_laps = pd.concat(driver_laps_per_session)
        driver_laps = driver_laps.reset_index()

        # --- Plotting Setup ---
        # Determine the order of drivers on the x-axis based on their abbreviation.
        # This ensures the plot is ordered logically (e.g., by team or finishing position).
        driver_order = [session_list[-1].get_driver(i)["Abbreviation"] for i in drivers]

        # Initialize the matplotlib figure and axes.
        fig, ax = plt.subplots(figsize=(21, 9))
        fig.tight_layout()

        # Convert the 'LapTime' (timedelta) to total seconds for plotting on a numeric axis.
        driver_laps["LapTime(s)"] = driver_laps["LapTime"].dt.total_seconds()

        # --- Plotting ---
        # 1. Create the violin plot to show the distribution of lap times for each driver.
        sns.violinplot(data=driver_laps,
                    x="Driver", y="LapTime(s)", hue="Driver",
                    inner=None, # Hides the inner box/stick plot inside the violin.
                    density_norm="area", # Ensures violins have the same area.
                    order=driver_order,
                    palette=fastf1.plotting.get_driver_color_mapping(session=session_list[-1])
                    )

        # 2. Overlay a swarm plot to show each individual lap.
        #    Each point is colored by the tyre compound used for that lap.
        sns.swarmplot(data=driver_laps,
                    x="Driver", y="LapTime(s)",
                    order=driver_order,
                    hue="Compound",
                    palette=fastf1.plotting.get_compound_mapping(session=session_list[-1]),
                    hue_order=["WET", "INTERMEDIATE", "SOFT", "MEDIUM", "HARD"], # Fixed compound order
                    linewidth=0,
                    size=3,
                    )
        
        # --- Final Touches & Sending ---
        # Save the generated plot to an in-memory binary stream (BytesIO).
        bio = io.BytesIO()
        fig.savefig(bio, dpi=600, format="png")
        # Reset the stream's position to the beginning before reading.
        bio.seek(0)
        # Create a discord.File object from the stream.
        attachment = discord.File(bio, filename="pace.png")
        
        # Send the file as a response to the interaction.
        await interaction.followup.send(file=attachment)
        return
