# command.py

import discord
from discord import app_commands # <--- This module handles Application Commands, including Slash Commands
import os
import fastf1
import datetime
import logging
import pandas as pd
from dotenv import load_dotenv

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

async def track_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Provides autocomplete suggestions for track names based on files in TRACKS_DIR."""
    current_year = datetime.datetime.now(datetime.timezone.utc).year
    event_schedule = fastf1.get_event_schedule(current_year, include_testing=False)
    choices = [app_commands.Choice(name=event_name, value=location) for event_name, location in list(zip(event_schedule["EventName"], event_schedule["Location"])) ]
    log.debug(f"Autocomplete for '{current}': Found {len(choices)} choices.")
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

    # Defines the /strategist nextrace Slash Command
    @app_commands.command(name="nextrace", description="Get the schedule for the next F1 race.") # <--- Defines a Slash Command
    async def next_race(self, interaction: discord.Interaction):
        """Fetches and displays the schedule for the upcoming F1 race weekend using get_events_remaining."""
        log.info(f"Command '/strategist nextrace' invoked by {interaction.user}")
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Get current time in UTC for accurate comparison
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            log.info(f"Fetching remaining F1 events after {now_utc} using FastF1...")

            # Use fastf1.get_events_remaining() to get future events directly
            # It returns a DataFrame sorted chronologically.
            # remaining_events = fastf1.get_events_remaining(now_utc, include_testing=False)
            remaining_events = fastf1.get_events_remaining(include_testing=False)

            next_race_event = None
            # Check if the DataFrame is not empty (i.e., there are remaining events)
            if not remaining_events.empty:
                # The first row (.iloc[0]) is the next event
                next_race_event = remaining_events.iloc[0]
                log.info(f"Found next race using get_events_remaining: Round {next_race_event['RoundNumber']} - {next_race_event['EventName']}")
            else:
                # Handle case where no races are left in the season
                current_year = now_utc.year # Get year for the message
                log.info(f"No upcoming races found using get_events_remaining for the {current_year} season after {now_utc}.")

            # Proceed with formatting and sending the message if an event was found
            if next_race_event is not None:
                # Helper function to generate Discord timestamp string
                def get_discord_timestamp(session_time_utc):
                    if pd.isna(session_time_utc):
                        return "N/A"
                    # Convert pandas Timestamp to Unix timestamp (integer seconds)
                    unix_ts = int(session_time_utc.timestamp())
                    # Format using Discord's timestamp codes
                    # <t:unix_ts:F> = Full Date and Time (e.g., Tuesday, April 8, 2025 9:09 PM)
                    # <t:unix_ts:R> = Relative Time (e.g., in 2 days)
                    return f"<t:{unix_ts}:F> (<t:{unix_ts}:R>)"

                # Build the response message using Discord timestamps
                response_message = (
                    f"📅 **Next F1 Event: {next_race_event['EventName']} (Round {next_race_event['RoundNumber']})**\n"
                    f"📍 Location: {next_race_event['Location']}, {next_race_event['Country']}\n\n"
                    f"🗓️ **Schedule (Displayed in your local time):**\n"
                    # Using the helper function to generate Discord timestamps
                    f" L: {get_discord_timestamp(next_race_event['Session1Date'])} - {next_race_event['Session1']}\n"
                    f" L: {get_discord_timestamp(next_race_event['Session2Date'])} - {next_race_event['Session2']}\n"
                    f" L: {get_discord_timestamp(next_race_event['Session3Date'])} - {next_race_event['Session3']}\n"
                    f" L: {get_discord_timestamp(next_race_event['Session4Date'])} - {next_race_event['Session4']}\n"
                    f" L: **{get_discord_timestamp(next_race_event['Session5Date'])}** - {next_race_event['Session5']}\n\n" # Race session highlighted
                    f"*Note: Session names might differ for Sprint weekends.*"
                )
                log.info(f"Sending schedule for {next_race_event['EventName']} to {interaction.user} using Discord timestamps.")
                await interaction.followup.send(response_message, ephemeral=True)
            else:
                # Send message indicating no upcoming races found
                current_year = now_utc.year # Get year again just in case
                await interaction.followup.send(
                    f"ℹ️ Couldn't find any upcoming F1 races scheduled for the rest of {current_year}.",
                    ephemeral=True
                )

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
    @app_commands.autocomplete(track=track_autocomplete) # Link the 'track' parameter to the autocomplete function
    async def trackmap(self, interaction: discord.Interaction, track: str):
        """Sends the specified track map image ephemerally."""
        log.info(f"Command '/strategist trackmap' invoked by {interaction.user} for track: {track}")
        # Defer response ephemerally
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Construct the expected file path
        file_path = os.path.join(TRACKS_DIR, f"{track}.png")
        log.debug(f"Looking for track map at: {file_path}")

        # Check if the file exists
        if os.path.exists(file_path):
            try:
                # Create a discord.File object and send it
                discord_file = discord.File(file_path)
                log.info(f"Sending track map '{track}.png' to {interaction.user}")
                await interaction.followup.send(file=discord_file) # Ephemeral is handled by defer
            except discord.HTTPException as e:
                log.error(f"Failed to send track map file '{file_path}': {e}", exc_info=True)
                await interaction.followup.send(f"❌ Failed to send the track map image due to a Discord error.") # Ephemeral handled by defer
            except Exception as e:
                log.error(f"An unexpected error occurred while sending track map '{file_path}': {e}", exc_info=True)
                await interaction.followup.send(f"❌ An unexpected error occurred while sending the track map.") # Ephemeral handled by defer
        else:
            # File not found
            log.warning(f"Track map file not found: {file_path}")
            await interaction.followup.send(f"❌ Sorry, I couldn't find the track map for '{track}'. Please ensure the file '{track}.png' exists in the '{TRACKS_DIR}' folder.") # Ephemeral handled by defer


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

