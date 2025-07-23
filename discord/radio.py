# radio.py
"""
Handles team radio messages from the Redis pub/sub stream and posts them to Discord.

This module listens for messages on the 'TeamRadio' channel, retrieves the relevant
driver information, and sends the radio transmission content to a specified
Discord webhook.
"""

import asyncio
import json
from typing import Any, Dict

import redis.asyncio as redis
from discordwebhook import Discord
from dotenv import load_dotenv

from utils import *

load_dotenv()

# --- Configuration ---
DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()


async def radioCaptureHandler(
    redis_client: redis.Redis, discord: Discord, capture: Dict[str, Any]
) -> None:
    """
    Processes a team radio capture and posts it to Discord.

    Args:
        redis_client: An active Redis client instance.
        discord: A Discord webhook client.
        capture: A dictionary containing the radio capture data.
    """
    # --- Data Fetching ---
    # Get driver information from Redis to add context to the message.
    driverInfo = (await redis_client.json().get("DriverList"))[capture["RacingNumber"]]

    # --- Message Processing and Sending ---
    # Post the radio message to Discord, including the driver's name, number, and team color.
    if message := capture.get("Message"): # Safely get the message
        discord.post(
            username=f"{driverInfo['BroadcastName']} - {capture['RacingNumber']}{VER_TAG}",
            embeds=[
                {
                    "fields": [
                        {
                            "name": "Team Radio",
                            "value": message["text"],
                            "inline": True,
                        },
                    ],
                    "color": int(driverInfo["TeamColour"], 16),
                }
            ],
            avatar_url=driverInfo.get("HeadshotUrl"), # Safely get the headshot URL
        )


async def connectRedisChannel() -> None:
    """
    Connects to the Redis server and subscribes to the TeamRadio channel.

    This function continuously listens for messages and calls the handler function.
    """
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("TeamRadio")
        async for payload in pubsub.listen():
            if payload["type"] == "message":
                channel = payload["channel"].decode("utf-8")
                if channel == "TeamRadio":
                    # The payload contains a list of radio captures; process each one.
                    for capture in json.loads(payload["data"])["Captures"]:
                        asyncio.create_task(
                            radioCaptureHandler(
                                redis_client, Discord(url=DISCORD_WEBHOOK), capture
                            )
                        )


if __name__ == "__main__":
    asyncio.run(connectRedisChannel())
