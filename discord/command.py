# command.py

import discord
from discord import app_commands # <--- This module handles Application Commands, including Slash Commands
import os
import fastf1
import datetime
import logging
import pandas as pd
from dotenv import load_dotenv
from typing import Optional

# --- Configuration ---
# Load environment variables early to get LOG_LEVEL
load_dotenv()

TRACKS_DIR = "data/tracks"

# Define valid log levels and map them to logging constants
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# Get log level from environment variable, default to 'WARNING' <--- Changed default
# Convert to upper case to make it case-insensitive
log_level_name = os.getenv('LOG_LEVEL', 'WARNING').upper()
# Get the corresponding logging level constant, default to WARNING if the name is invalid <--- Changed default
numeric_log_level = LOG_LEVELS.get(log_level_name, logging.WARNING)

# Set up logging using the determined level
logging.basicConfig(level=numeric_log_level, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
log = logging.getLogger(__name__) # Get the logger instance

# Log the actual level being used for confirmation
# This message itself is INFO level, so it will only show if the effective level is INFO or DEBUG
log.info(f"Logging level set to: {logging.getLevelName(numeric_log_level)}")

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

try:
    fastf1.Cache.enable_cache('fastf1_cache')
    log.info("FastF1 cache enabled successfully.")
except Exception as e:
    log.warning(f"Could not enable FastF1 cache (this is optional but recommended): {e}")

# --- Bot Setup ---
intents = discord.Intents.default()
client = discord.Client(intents=intents)
# CommandTree is essential for registering and handling Application Commands (Slash Commands)
tree = app_commands.CommandTree(client) # <--- This tree manages your Slash Commands

async def event_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Provides autocomplete suggestions for F1 event names in the current season."""
    choices = []
    try:
        current_year = datetime.datetime.now().year
        # Fetch schedule for autocomplete - cache helps performance here
        schedule = fastf1.get_event_schedule(current_year, include_testing=False)

        choices = [ app_commands.Choice(name=event_name, value=event_name) for event_name in schedule['EventName'].unique().tolist() ]

    except Exception as e:
        log.error(f"Error during event autocomplete: {e}", exc_info=True)
        # Consider sending an ephemeral message back if autocomplete fails critically?
        # For now, just return empty list on error.
    log.debug(f"Event autocomplete for '{current}': Found {len(choices)} choices.")
    return choices

# --- Command Groups (using Class-based structure for organization) ---
# app_commands.Group is used to create Slash Command groups (e.g., /strategist ...)
class RaceEngineerGroup(app_commands.Group): # <--- Defines a Slash Command Group
    """Encapsulates commands related to Race Engineering."""
    def __init__(self):
        super().__init__(name="race-engineer", description="Commands for the Race Engineer.")
        log.info("Race Engineer command group initialized.")

    # app_commands.command defines a specific Slash Command within the group (e.g., /race-engineer check_tyres)
    @app_commands.command(name="check_tyres", description="Placeholder: Check tyre status.") # <--- Defines a Slash Command
    async def check_tyres(self, interaction: discord.Interaction):
        """A placeholder command for the race engineer."""
        log.info(f"Command '/race-engineer check_tyres' invoked by {interaction.user}")
        await interaction.response.send_message(
            "Placeholder command: Checking tyre temperatures and wear...",
            ephemeral=True
        )

class StrategistGroup(app_commands.Group): # <--- Defines another Slash Command Group
    """Encapsulates commands related to Race Strategy."""
    def __init__(self):
        super().__init__(name="strategist", description="Commands for the Strategist.")
        log.info("Strategist command group initialized.")


    # --- schedule Command (replaces nextrace) ---
    @app_commands.command(name="schedule", description="Get the F1 schedule for a specific event, or the next upcoming event.")
    @app_commands.autocomplete(event_name=event_autocomplete) # Link autocomplete to the event_name parameter
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
                remaining_events = fastf1.get_events_remaining(include_testing=False) # Consider passing now_utc if needed
                if not remaining_events.empty:
                    target_event = remaining_events.iloc[0]
                    log.info(f"Found next upcoming event: {target_event['EventName']}")
                else:
                    log.warning(f"No upcoming races found for the {current_year} season after {now_utc}.")
                    error_message = f"ℹ️ Couldn't find any upcoming F1 races scheduled for the rest of {current_year}."

            # --- Send response ---
            if target_event is not None:
                # Format and send the schedule for the target_event
                def get_discord_timestamp(session_time_utc):
                    if pd.isna(session_time_utc): return "N/A"
                    unix_ts = int(session_time_utc.timestamp())
                    return f"<t:{unix_ts}:F> (<t:{unix_ts}:R>)"

                response_message = (
                    f"📅 **F1 Event: {target_event['EventName']} (Round {target_event['RoundNumber']})**\n"
                    f"📍 Location: {target_event['Location']}, {target_event['Country']}\n\n"
                    f"🗓️ **Schedule (Displayed in your local time):**\n"
                    f" L: {get_discord_timestamp(target_event['Session1Date'])} - {target_event['Session1']}\n"
                    f" L: {get_discord_timestamp(target_event['Session2Date'])} - {target_event['Session2']}\n"
                    f" L: {get_discord_timestamp(target_event['Session3Date'])} - {target_event['Session3']}\n"
                    f" L: {get_discord_timestamp(target_event['Session4Date'])} - {target_event['Session4']}\n"
                    f" L: **{get_discord_timestamp(target_event['Session5Date'])}** - {target_event['Session5']}\n\n"
                    f"*Note: Session names might differ for Sprint weekends.*"
                )
                log.info(f"Sending schedule for {target_event['EventName']} to {interaction.user}")
                await interaction.followup.send(response_message) # Ephemeral handled by defer

            elif error_message:
                # Send the specific error message determined above
                await interaction.followup.send(error_message) # Ephemeral handled by defer
            else:
                 # Fallback error if something unexpected happened
                 log.error("Reached end of schedule command logic without finding an event or specific error.")
                 await interaction.followup.send("❌ An unexpected issue occurred while retrieving the schedule.") # Ephemeral handled by defer


        except Exception as e:
            # General error handling for the command
            log.error(f"Error executing '/strategist schedule': {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred while fetching the F1 schedule: {e}") # Ephemeral handled by defer

        except Exception as e:
            # General error handling for the command
            log.error(f"Error executing '/strategist nextrace': {e}", exc_info=True) # Log detailed traceback
            await interaction.followup.send(
                f"❌ An error occurred while fetching the F1 race schedule. Please try again later.\n"
                f"`Error: {e}`",
                ephemeral=True
            )

    # --- trackmap Command ---
    @app_commands.command(name="trackmap", description="Displays the map for a specific F1 track.")
    @app_commands.autocomplete(event_name=event_autocomplete) # Link the 'event_name' parameter to the autocomplete function
    async def trackmap(self, interaction: discord.Interaction, event_name: str):
        """Sends the specified track map image ephemerally."""
        log.info(f"Command '/strategist trackmap' invoked by {interaction.user} for event: {event_name}")
        # Defer response ephemerally while we fetch/process
        await interaction.response.defer(ephemeral=True, thinking=True)

        track_location = None
        file_path = None
        error_message = None # Variable to hold specific error messages

        try:
            # --- 1. Fetch Schedule and Find Event ---
            current_year = datetime.datetime.now().year
            log.info(f"Fetching schedule for specified event: {event_name}")
            target_event = fastf1.get_event(current_year, event_name)
            track_location = target_event['Location']
            

            # --- 2. Construct File Path (only if event was found and no prior error) ---
            if track_location and not error_message:
                file_path = os.path.join(TRACKS_DIR, f"{track_location}.png")
                log.debug(f"Constructed track map path: {file_path}")

                # --- 3. Check File Existence (only if path constructed and no prior error) ---
                if not os.path.exists(file_path):
                    log.warning(f"Track map file not found at: {file_path}")
                    error_message = f"❌ Sorry, I couldn't find the track map for '{track_location}'. Please ensure the file '{track_location}.png' exists in the '{TRACKS_DIR}' directory."
                    file_path = None # Prevent attempting to send

        # --- Catch errors during the setup phase (schedule fetch, path construction, file check) ---
        except fastf1.ErgastError as e:
             log.error(f"FastF1 Ergast API error while fetching schedule for trackmap: {e}", exc_info=True)
             error_message = f"❌ Failed to fetch F1 schedule data from the Ergast API. Please try again later."
             file_path = None # Ensure we don't proceed
        except ConnectionError as e:
             log.error(f"Network error during FastF1 operation for trackmap: {e}", exc_info=True)
             error_message = f"❌ A network error occurred while trying to get F1 data. Please check your connection and try again."
             file_path = None # Ensure we don't proceed
        except Exception as e:
            # Catch-all for other unexpected errors during setup
            log.error(f"Unexpected error in '/strategist trackmap' during setup: {e}", exc_info=True)
            error_message = f"❌ An unexpected error occurred while processing your request for the track map."
            file_path = None # Ensure we don't proceed


        # --- 4. Attempt to Send File (only if path is valid and no errors occurred during setup) ---
        if file_path and not error_message:
            try:
                discord_file = discord.File(file_path)
                log.info(f"Sending track map '{file_path}' to {interaction.user}")
                await interaction.followup.send(file=discord_file) # Ephemeral is handled by defer
                return # Success, exit the function

            # --- Catch errors specifically related to sending the file ---
            except discord.HTTPException as e:
                log.error(f"Discord API error sending track map file '{file_path}': {e}", exc_info=True)
                error_message = f"❌ Failed to send the track map image due to a Discord error. Please try again later."
            except FileNotFoundError: # Should be caught by os.path.exists, but good failsafe
                 log.error(f"File not found error during discord.File creation for '{file_path}' (should have been caught earlier).")
                 error_message = f"❌ An unexpected error occurred: Could not find the track map file '{track_location}.png'."
            except PermissionError:
                log.error(f"Permission error reading track map file '{file_path}'.")
                error_message = f"❌ An error occurred: I don't have permission to read the track map file '{track_location}.png'."
            except Exception as e:
                log.error(f"Unexpected error sending track map '{file_path}': {e}", exc_info=True)
                error_message = f"❌ An unexpected error occurred while trying to send the track map."

        # --- 5. Send Error Message (if any error occurred at any stage) ---
        if error_message:
            # Check if the interaction has already been responded to (e.g., by the defer)
            # followup.send is generally safe after defer, but this check can prevent issues in complex scenarios
            # if not interaction.response.is_done(): # This check might not be strictly necessary with defer->followup
            #     await interaction.response.send_message(error_message, ephemeral=True)
            # else:
            await interaction.followup.send(error_message) # Ephemeral handled by defer

# --- Bot Events ---
@client.event
async def on_ready():
    """Event triggered when the bot successfully connects to Discord and is ready."""
    log.info(f'Logged in as {client.user.name} (ID: {client.user.id})')
    log.info(f'discord.py version: {discord.__version__}')
    log.info(f'fastf1 version: {fastf1.__version__}')
    log.info('------')

    # Add the command group instances to the command tree
    tree.add_command(RaceEngineerGroup())
    tree.add_command(StrategistGroup())
    log.info("Command groups added to the command tree.")

    # Sync the command tree with Discord's servers.
    # This makes the Slash Commands appear for users.
    try:
        synced = await tree.sync() # <--- Syncs the defined Slash Commands with Discord
        log.info(f"Synced {len(synced)} command(s) globally.")
        # --- OR Sync to a specific guild for testing ---
        # GUILD_ID = 123456789012345678 # Replace with your test server's ID
        # guild_object = discord.Object(id=GUILD_ID)
        # synced = await tree.sync(guild=guild_object)
        # log.info(f"Synced {len(synced)} command(s) to guild {GUILD_ID}.")
    except Exception as e:
        log.error(f"Failed to sync command tree: {e}", exc_info=True)

    # Use logger instead of print for the final ready message
    log.info(f"--- Bot {client.user} is ready! ---") # <--- Changed from print

# --- Run the Bot ---
if __name__ == "__main__":
    # Check if the vital Discord bot token is actually set
    if DISCORD_BOT_TOKEN is None:
        # Use logger for critical error messages
        log.critical("="*60) # <--- Changed from print
        log.critical("FATAL ERROR: DISCORD_BOT_TOKEN environment variable not set.") # <--- Changed from print
        log.critical("Please create a file named '.env' in the same directory as this script") # <--- Changed from print
        log.critical("and add the line: DISCORD_BOT_TOKEN='your_actual_bot_token'") # <--- Changed from print
        log.critical("Alternatively, set it as a system environment variable.") # <--- Changed from print
        log.critical("="*60) # <--- Changed from print
    else:
        try:
            log.info("Attempting to connect to Discord...")
            # Start the bot using the token
            client.run(DISCORD_BOT_TOKEN, log_handler=None) # Keep log_handler=None if using basicConfig
        except discord.LoginFailure:
            # Use logger for critical login failure
            log.critical("FATAL ERROR: Improper token passed. Check the DISCORD_BOT_TOKEN value.") # <--- Changed from print
            log.critical("Failed to log in. The provided DISCORD_BOT_TOKEN is invalid.") # <--- Changed from print
        except Exception as e:
            # Use logger for other critical startup errors
            log.critical(f"FATAL ERROR: An unexpected error occurred during bot execution: {e}", exc_info=True) # <--- Changed from print
            log.critical(f"An unexpected startup error occurred: {e}") # <--- Changed from print

