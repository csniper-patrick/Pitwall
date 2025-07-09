# strategist_group.py

import discord
from discord import app_commands
import os
import fastf1
import datetime
import logging
import pandas as pd
from typing import Optional

# Get a logger instance for this module
log = logging.getLogger(__name__)

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
                # Helper to format session times into Discord timestamps
                def get_discord_timestamp(session_time_utc):
                    if pd.isna(session_time_utc): return "N/A"
                    unix_ts = int(session_time_utc.timestamp())
                    return f"<t:{unix_ts}:F> (<t:{unix_ts}:R>)"

                response_message = (
                    f"📅 **F1 Event: {target_event['EventName']} (Round {target_event['RoundNumber']})**\n"
                    f"📍 Location: {target_event['Location']}, {target_event['Country']}\n\n"
                    f"🗓️ **Schedule (Displayed in your local time):**\n"
                    f" L: {get_discord_timestamp(target_event.get('Session1Date'))} - {target_event['Session1']}\n"
                    f" L: {get_discord_timestamp(target_event.get('Session2Date'))} - {target_event['Session2']}\n"
                    f" L: {get_discord_timestamp(target_event.get('Session3Date'))} - {target_event['Session3']}\n"
                    f" L: {get_discord_timestamp(target_event.get('Session4Date'))} - {target_event['Session4']}\n"
                    f" L: **{get_discord_timestamp(target_event.get('Session5Date'))}** - {target_event['Session5']}\n\n"
                    f"*Note: Session names might differ for Sprint weekends.*"
                )
                log.info(f"Sending schedule for {target_event['EventName']} to {interaction.user}")
                await interaction.followup.send(response_message)
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
