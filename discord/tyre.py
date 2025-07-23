# tyre.py
"""
Handles tyre stint updates from the Redis pub/sub stream and posts them to Discord.

This module listens for messages on the 'TyreStintSeries' channel, and when a new
stint is detected (indicating a tyre change), it sends a notification to a
specified Discord webhook with details about the new tyre compound and stint number.
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


async def tyresStintSeriesHandler(
    redis_client: redis.Redis,
    discord: Discord,
    raceNumber: str,
    delta: Dict[str, Any],
) -> None:
    """
    Processes tyre stint updates and sends a notification for tyre changes.

    Args:
        redis_client: An active Redis client instance.
        discord: A Discord webhook client.
        raceNumber: The racing number of the driver.
        delta: A dictionary containing the tyre stint update.
    """
    # --- Data Fetching ---
    sessionInfo = await redis_client.json().get("SessionInfo")
    if sessionInfo["Type"] not in ["Race", "Sprint"]:
        return

    driverInfo = (await redis_client.json().get("DriverList"))[raceNumber]
    tyreStint = (await redis_client.json().get("TyreStintSeries"))["Stints"][raceNumber]

    # --- Message Processing and Sending ---
    for idx, stint in delta.items():
        if "Compound" in stint:
            fullStintData = tyreStint[int(idx)]
            # Format the compound name with a symbol if available.
            if stint["Compound"] in msgStyle["compoundSymbol"]:
                currentCompound = f"{msgStyle['compoundSymbol'][stint['Compound']]}{stint['Compound']}"
            else:
                currentCompound = stint["Compound"]

            discord.post(
                username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
                embeds=[
                    {
                        "title": f"Tyre Change - {currentCompound}",
                        "fields": [
                            {"name": "Stint", "value": int(idx) + 1, "inline": True},
                            {
                                "name": "Age",
                                "value": fullStintData["StartLaps"],
                                "inline": True,
                            },
                        ],
                        "color": msgStyle["compoundColor"].get(stint["Compound"]),
                    }
                ],
                avatar_url=driverInfo.get("HeadshotUrl"),
            )


async def connectRedisChannel() -> None:
    """
    Connects to the Redis server and subscribes to the TyreStintSeries channel.

    This function continuously listens for messages and calls the handler function.
    """
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("TyreStintSeries")
        async for payload in pubsub.listen():
            if payload["type"] == "message":
                channel = payload["channel"].decode("utf-8")
                if channel == "TyreStintSeries":
                    stints = json.loads(payload["data"])["Stints"]
                    for raceNumber, delta in stints.items():
                        if isinstance(delta, dict):
                            asyncio.create_task(
                                tyresStintSeriesHandler(
                                    redis_client,
                                    Discord(url=DISCORD_WEBHOOK),
                                    raceNumber,
                                    delta,
                                )
                            )


if __name__ == "__main__":
    asyncio.run(connectRedisChannel())
