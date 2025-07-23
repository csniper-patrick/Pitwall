# pitlane.py
"""
Handles pit lane-related events from the Redis pub/sub stream and posts them to Discord.

This module listens for messages on the 'PitLaneTimeCollection' and 'PitStop' channels,
processes them, and sends formatted notifications to a specified Discord webhook.
It specifically handles slow pit stops and regular pit stop announcements.
"""

import asyncio
import json
import re
from collections import defaultdict
from typing import Any, Dict

import redis.asyncio as redis
from discordwebhook import Discord
from dotenv import load_dotenv

from utils import *

load_dotenv()

# --- Configuration ---
DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

# Load pit time reference statistics from a JSON file.
# This data is used to determine if a pit stop is slow.
pit_time_reference = defaultdict(lambda: dict(mean=25.0, std=5.0))
with open("data/pit-time-stat.json", "r") as file:
    for circuit, stat in json.load(file).items():
        pit_time_reference[circuit]["mean"] = stat["mean"]
        pit_time_reference[circuit]["std"] = stat["std"]


async def pitLaneTimeCollectionHandler(
    redis_client: redis.Redis, discord: Discord, raceNumber: str, delta: Dict[str, Any]
) -> None:
    """
    Handles messages about the time a driver spends in the pit lane.

    If a driver's time in the pit lane exceeds a certain threshold (z-score > 1),
    it is considered a slow stop, and a notification is sent to Discord.

    Args:
        redis_client: An active Redis client instance.
        discord: A Discord webhook client.
        raceNumber: The racing number of the driver.
        delta: A dictionary containing the pit lane time data.
    """
    # Ensure the message is for the correct driver and session type.
    if "RacingNumber" not in delta or raceNumber != delta["RacingNumber"]:
        return
    sessionInfo = await redis_client.json().get("SessionInfo")
    if sessionInfo["Type"] not in ["Race", "Sprint"]:
        return

    # --- Data Fetching & Processing ---
    driverInfo = (await redis_client.json().get("DriverList"))[raceNumber]
    # Convert the duration string (e.g., "25.5s") to seconds.
    durationSec = reversed([float(i) for i in re.split(":", delta["Duration"])])
    durationSec = sum([val * scaler for val, scaler in zip(durationSec, [1, 60])])
    circuit = sessionInfo["Meeting"]["Circuit"]["ShortName"]
    # Calculate the z-score to identify slow pit stops.
    z_score_1 = pit_time_reference[circuit]["mean"] + pit_time_reference[circuit]["std"]

    # --- Send Notification ---
    # If the pit stop is slower than the threshold and not excessively long (e.g., due to a red flag),
    # send a "Slow Pit Stop" notification.
    if durationSec >= z_score_1 and durationSec <= 600.0:
        discord.post(
            username=f"{driverInfo['TeamName']}{VER_TAG}",
            embeds=[
                {
                    "title": f"Slow Pit Stop - {delta['Duration']} in pit lane",
                    "fields": [
                        {
                            "name": "Driver",
                            "value": driverInfo["FullName"],
                            "inline": True,
                        },
                    ],
                    "color": int(driverInfo["TeamColour"], 16),
                }
            ],
        )


async def pitStopHandler(
    redis_client: redis.Redis, discord: Discord, message: Dict[str, Any]
) -> None:
    """
    Handles messages about a driver's pit stop.

    This function sends a notification to Discord for every pit stop event.

    Args:
        redis_client: An active Redis client instance.
        discord: A Discord webhook client.
        message: A dictionary containing the pit stop data.
    """
    # Ensure the session is a race or sprint.
    sessionInfo = await redis_client.json().get("SessionInfo")
    if sessionInfo["Type"] not in ["Race", "Sprint"]:
        return

    # --- Data Fetching ---
    driverInfo = (await redis_client.json().get("DriverList"))[message["RacingNumber"]]

    # --- Send Notification ---
    discord.post(
        username=f"{driverInfo['TeamName']}{VER_TAG}",
        embeds=[
            {
                "title": f"Pit Stop - {message['PitStopTime']}",
                "fields": [
                    {
                        "name": "Driver",
                        "value": driverInfo["FullName"],
                        "inline": True,
                    },
                ],
                "color": int(driverInfo["TeamColour"], 16),
            }
        ],
    )
    return


async def connectRedisChannel() -> None:
    """
    Connects to the Redis server and subscribes to relevant pub/sub channels.

    This function continuously listens for messages on the 'PitLaneTimeCollection'
    and 'PitStop' channels and calls the appropriate handler function.
    """
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("PitLaneTimeCollection", "PitStop")
        async for payload in pubsub.listen():
            if payload["type"] == "message":
                channel = payload["channel"].decode("utf-8")
                if channel == "PitLaneTimeCollection":
                    pitTimes = json.loads(payload["data"])["PitTimes"]
                    for raceNumber, delta in pitTimes.items():
                        asyncio.create_task(
                            pitLaneTimeCollectionHandler(
                                redis_client,
                                Discord(url=DISCORD_WEBHOOK),
                                raceNumber,
                                delta,
                            )
                        )
                elif channel == "PitStop":
                    pitStop = json.loads(payload["data"])
                    asyncio.create_task(
                        pitStopHandler(
                            redis_client, Discord(url=DISCORD_WEBHOOK), pitStop
                        )
                    )


if __name__ == "__main__":
    asyncio.run(connectRedisChannel())
