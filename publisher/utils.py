# publisher/utils.py
"""
Utility functions for the publisher services.
"""

import os
import re
import urllib.parse
from typing import Any, Dict, Tuple


def updateDictDelta(obj: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively updates a dictionary with the values from another dictionary.

    This is used to apply delta updates received from the live timing API to the
    full data structures stored in Redis.

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


def timeStr2msec(timeStr: str) -> float:
    """
    Converts a time string (e.g., "1:23.456") to milliseconds.

    Args:
        timeStr: The time string to convert.

    Returns:
        The time in milliseconds.
    """
    parts = re.split(r"[:.]", timeStr)
    m, s, ms = (parts + ['0'] * 3)[:3] # Pad with zeros if parts are missing
    return (int(m) * 60 + int(s)) * 1000 + int(ms)


def msec2timeStr(msec: int, signed: bool = False) -> str:
    """
    Converts milliseconds to a time string (e.g., "1:23.456").

    Args:
        msec: The time in milliseconds.
        signed: Whether to include a '+' sign for positive values.

    Returns:
        The formatted time string.
    """
    val = abs(int(msec))
    if signed:
        timeStr = "+" if msec >= 0 else "-"
    else:
        timeStr = "" if msec >= 0 else "-"

    minutes = val // 60000
    seconds = (val % 60000) // 1000
    milliseconds = val % 1000

    if minutes > 0:
        return f"{timeStr}{minutes}:{seconds:02}.{milliseconds:03}"
    return f"{timeStr}{seconds}.{milliseconds:03}"


def load_config() -> Tuple[bool, str, bool, str, str, str, float, str, int, str]:
    """
    Loads configuration settings from environment variables.

    This centralizes the configuration for all publisher services.

    Returns:
        A tuple containing the loaded configuration settings.
    """
    # --- General Settings ---
    USE_SSL = os.getenv("USE_SSL", default="True").lower() == "true"
    API_HOST = os.getenv("API_HOST", default="livetiming.formula1.com")
    RETRY = os.getenv("RETRY", default="True").lower() == "true"

    # --- URL Construction ---
    # Build the base URLs for the live timing API.
    base_http_url = f"https://{API_HOST}" if USE_SSL else f"http://{API_HOST}"
    base_ws_url = f"wss://{API_HOST}" if USE_SSL else f"ws://{API_HOST}"

    livetimingUrl = urllib.parse.urljoin(base_http_url, "/signalr")
    websocketUrl = urllib.parse.urljoin(base_ws_url, "/signalr")
    staticUrl = urllib.parse.urljoin(base_http_url, "/static")

    # --- Redis Configuration ---
    REDIS_HOST = os.getenv("REDIS_HOST", default="redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", default=6379))
    REDIS_CHANNEL = "RACE_CONTROL" # Note: This is a default and may not be used by all publishers.

    # --- SignalR Client Configuration ---
    clientProtocol = 1.5

    return (
        USE_SSL,
        API_HOST,
        RETRY,
        livetimingUrl,
        websocketUrl,
        staticUrl,
        clientProtocol,
        REDIS_HOST,
        REDIS_PORT,
        REDIS_CHANNEL,
    )
