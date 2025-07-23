# race-control.py
"""
Handles Race Control messages from the Redis pub/sub stream and posts them to Discord.

This module listens for messages on the 'RaceControlMessages' channel, formats them
into Discord embeds with appropriate colors and symbols based on the message type
(e.g., flags, safety car deployments), and sends them to a specified Discord webhook.
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


async def raceControlMessageHandler(
    redis_client: redis.Redis, discord: Discord, messages: Dict[str, Any]
) -> None:
    """
    Processes and formats Race Control messages for posting to Discord.

    Args:
        redis_client: An active Redis client instance.
        discord: A Discord webhook client.
        messages: A dictionary containing the Race Control messages.
    """
    # --- Style Configuration ---
    flagColor = msgStyle["flagColor"]
    flagSymbol = msgStyle["flagSymbol"]
    modeColor = msgStyle["modeColor"]

    # Ensure messages are in a list format.
    if isinstance(messages["Messages"], dict):
        messages["Messages"] = list(messages["Messages"].values())

    # --- Message Processing and Sending ---
    for content in messages["Messages"]:
        # Skip blue flags as they are too frequent and not critical for general viewing.
        if content.get("Flag") == "BLUE":
            continue

        # Add a flag symbol to the message if applicable.
        if content.get("Flag") in flagSymbol:
            content["Message"] = f"{flagSymbol[content['Flag']]}{content['Message']}"

        # Determine the color of the embed based on the flag or mode.
        embed_color = None
        if content.get("Flag") in flagColor:
            embed_color = flagColor[content["Flag"]]
        elif content.get("Mode") in modeColor:
            embed_color = modeColor[content["Mode"]]

        discord.post(
            username=f"{msgStyle['raceDirector']}{VER_TAG}",
            embeds=[
                {
                    "title": content["Message"],
                    "fields": [
                        {"name": key, "value": value, "inline": True}
                        for key, value in content.items()
                        if key in ["Mode", "Status"]
                    ],
                    "color": embed_color,
                }
            ],
        )


async def connectRedisChannel() -> None:
    """
    Connects to the Redis server and subscribes to the RaceControlMessages channel.

    This function continuously listens for messages and calls the handler function.
    """
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("RaceControlMessages")
        async for payload in pubsub.listen():
            if payload["type"] == "message":
                channel = payload["channel"].decode("utf-8")
                if channel == "RaceControlMessages":
                    asyncio.create_task(
                        raceControlMessageHandler(
                            redis_client,
                            Discord(url=DISCORD_WEBHOOK),
                            json.loads(payload["data"]),
                        )
                    )


if __name__ == "__main__":
    asyncio.run(connectRedisChannel())
