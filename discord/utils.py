# utils.py
"""
Provides utility functions for the Pitwall Discord bot, including configuration
loading and dictionary manipulation.
"""

import json
import os
from typing import Any, Dict, Tuple


def updateDictDelta(obj: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively updates a dictionary with the values from another dictionary.

    Args:
        obj: The dictionary to be updated.
        delta: The dictionary containing the new values.

    Returns:
        The updated dictionary.
    """
    for key, value in delta.items():
        if key not in obj:
            obj[key] = value
        elif isinstance(value, dict) and isinstance(obj.get(key), dict):
            obj[key] = updateDictDelta(obj[key], value)
        elif isinstance(value, dict) and isinstance(obj.get(key), list):
            # This handles cases where a list of dictionaries is updated by index.
            tempDict = {str(idx): val for idx, val in enumerate(obj[key])}
            tempDict = updateDictDelta(tempDict, value)
            obj[key] = list(tempDict.values())
        else:
            obj[key] = value
    return obj


def load_config() -> Tuple[str, str, Dict[str, Any], str, int, str, bool]:
    """
    Loads configuration settings from environment variables and a JSON style file.

    Returns:
        A tuple containing the loaded configuration settings.
    """
    # --- Discord Configuration ---
    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
    VER_TAG = os.getenv("VER_TAG", default="")

    # --- Message Styling ---
    MSG_STYLE_PATH = os.getenv("MSG_STYLE_PATH", default="./style.json")
    # Default style settings
    msgStyle = {
        "flagColor": {
            "GREEN": 5763719,
            "CLEAR": 5763719,
            "YELLOW": 16776960,
            "DOUBLE YELLOW": 16776960,
            "CHEQUERED": 16777215,
            "BLUE": 3447003,
            "RED": 15548997,
            "BLACK AND WHITE": 16777215,
            "BLACK AND ORANGE": 15105570,
            "BLACK": 2303786,
        },
        "flagSymbol": {"CHEQUERED": ":checkered_flag:", "BLACK": ":flag_black:"},
        "modeColor": {
            "SAFETY CAR": 15844367,
            "SC": 15844367,
            "VIRTUAL SAFETY CAR": 15844367,
            "VSC": 15844367
        },
        "compoundColor": {
            "SOFT": 15548997,  # RED
            "MEDIUM": 16776960,  # YELLOW
            "HARD": 16777215,  # WHITE
            "INTERMEDIATE": 2067276,  # GREEN
            "WET": 2123412,  # BLUE
        },
        "compoundRGB": {
            "WET": "#0067ad",
            "INTERMEDIATE": "#43b02a",
            "SOFT": "#da291c",
            "MEDIUM": "#ffd12e",
            "HARD": "#f0f0ec",
        },
        "compoundSymbol": {},
        "raceDirector": "Race Director",
    }
    # Load and merge custom styles from the JSON file if it exists.
    if os.path.isfile(MSG_STYLE_PATH):
        with open(MSG_STYLE_PATH) as f:
            msgStyle = updateDictDelta(msgStyle, json.load(f))

    # --- Redis Configuration ---
    REDIS_HOST = os.getenv("REDIS_HOST", default="redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", default=6379))
    REDIS_CHANNEL = "RACE_CONTROL"

    RETRY = os.getenv("RETRY", default="True").lower() == "true"

    return DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY
