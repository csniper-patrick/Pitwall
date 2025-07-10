# command.py

import discord
from discord import app_commands
import os
import fastf1
import logging
from dotenv import load_dotenv

# --- Import Command Groups from their separate files ---
from race_engineer_group import RaceEngineerGroup
from strategist_group import StrategistGroup

# --- Configuration ---
# Load environment variables from a .env file
load_dotenv()

# Define valid log levels and map them to logging constants
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# Get log level from environment variable, default to 'WARNING'
log_level_name = os.getenv('LOG_LEVEL', 'WARNING').upper()
numeric_log_level = LOG_LEVELS.get(log_level_name, logging.WARNING)

# Set up logging using the determined level
logging.basicConfig(level=numeric_log_level, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
log = logging.getLogger(__name__)

log.info(f"Logging level set to: {logging.getLevelName(numeric_log_level)}")

# Get the bot token from environment variables
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Enable FastF1's cache
try:
    fastf1.Cache.enable_cache('fastf1_cache')
    log.info("FastF1 cache enabled successfully.")
except Exception as e:
    log.warning(f"Could not enable FastF1 cache (this is optional but recommended): {e}")

# --- Bot Setup ---
# Define the bot's intents
intents = discord.Intents.default()
client = discord.Client(intents=intents)
# CommandTree is essential for registering and handling Slash Commands
tree = app_commands.CommandTree(client)

# --- Command Groups ---
# Instantiate command groups to be used by the bot
COMMAND_GROUPS = [
    StrategistGroup(),
    RaceEngineerGroup()
]

# --- Help Command ---
@tree.command(name="pitwall-help", description="Shows a list of all available commands.")
async def help_command(interaction: discord.Interaction):
    """Displays a helpful message listing all commands."""
    log.info(f"Command '/pitwall-help' invoked by {interaction.user}")

    embed = discord.Embed(
        title="Pitwall Commands",
        description="Here are all the commands you can use with the Pitwall bot:",
        color=discord.Color.blurple()
    )

    # Add the help command itself to the list
    embed.add_field(
        name="General Commands",
        value="`/pitwall-help`: Shows this help message.\n\n"
            "Output of all the following commands are only visible to you",
        inline=False
    )

    for group in COMMAND_GROUPS:
        if isinstance(group, app_commands.Group):
            # Format command names and descriptions for the embed
            cmds = [f"`/{group.name} {cmd.name}`: {cmd.description}\n" for cmd in group.commands]
            if cmds:
                # Create a nice title from the group name (e.g., 'race-engineer' -> 'Race Engineer')
                group_name_title = ' '.join(word.capitalize() for word in group.name.split('-'))
                embed.add_field(
                    name=f"{group_name_title} Commands",
                    value="\n".join(cmds),
                    inline=False
                )

    # Add a field for project contribution
    embed.add_field(
        name="❤️ Support & 💪🏻Contribute",
        value="Pitwall is an open-source project! If you find it useful, please consider starring the project or contributing with code\n"
              "- [GitLab - Pitwall](https://gitlab.com/CSniper/pitwall)\n"
              "- [GitHub - Pitwall(mirror)](https://github.com/csniper-patrick/Pitwall)\n",
        inline=False
    )

    embed.set_footer(text="Use `/` to see all commands and their options in Discord.")
    await interaction.response.send_message(embed=embed, ephemeral=False)

# --- Bot Events ---
@client.event
async def on_ready():
    """Event triggered when the bot successfully connects to Discord and is ready."""
    log.info(f'Logged in as {client.user.name} (ID: {client.user.id})')
    log.info(f'discord.py version: {discord.__version__}')
    log.info(f'fastf1 version: {fastf1.__version__}')
    log.info('------')

    # Add the command groups to the command tree
    for group in COMMAND_GROUPS:
        tree.add_command(group)
    log.info("Command groups added to the command tree.")

    # Sync the command tree with Discord's servers to make slash commands appear.
    try:
        synced = await tree.sync()
        log.info(f"Synced {len(synced)} command(s) globally.")
    except Exception as e:
        log.error(f"Failed to sync command tree: {e}", exc_info=True)

    log.info(f"--- Bot {client.user} is ready! ---")

# --- Run the Bot ---
if __name__ == "__main__":
    # Check if the Discord bot token is set
    if DISCORD_BOT_TOKEN is None:
        log.critical("="*60)
        log.critical("FATAL ERROR: DISCORD_BOT_TOKEN environment variable not set.")
        log.critical("Please create a file named '.env' in the same directory")
        log.critical("and add the line: DISCORD_BOT_TOKEN='your_actual_bot_token'")
        log.critical("="*60)
    else:
        try:
            log.info("Attempting to connect to Discord...")
            # Start the bot using the token
            client.run(DISCORD_BOT_TOKEN, log_handler=None)
        except discord.LoginFailure:
            log.critical("FATAL ERROR: Improper token passed. Check the DISCORD_BOT_TOKEN value.")
        except Exception as e:
            log.critical(f"FATAL ERROR: An unexpected error occurred during bot execution: {e}", exc_info=True)
