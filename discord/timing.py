# timing.py
"""
Handles timing data events from the Redis pub/sub stream and posts them to Discord.

This module listens for messages on the 'TimingDataF1' channel and sends notifications
for various events, including fastest laps, personal bests, retirements, and
qualifying knockouts.
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


async def timingDataF1Handler(
    redis_client: redis.Redis, discord: Discord, raceNumber: str, delta: Dict[str, Any]
) -> None:
    """
    Processes timing data updates for a specific driver and sends notifications.

    Args:
        redis_client: An active Redis client instance.
        discord: A Discord webhook client.
        raceNumber: The racing number of the driver.
        delta: A dictionary containing the timing data update.
    """
    # --- Data Fetching ---
    sessionInfo = await redis_client.json().get("SessionInfo")
    timingDataF1 = (await redis_client.json().get("TimingDataF1"))["Lines"][raceNumber]
    driverInfo = (await redis_client.json().get("DriverList"))[raceNumber]
    tyreStint = (await redis_client.json().get("TyreStintSeries"))["Stints"].get(raceNumber, [])

    currentCompound = ""
    if tyreStint and tyreStint[-1].get("Compound") in msgStyle["compoundSymbol"]:
        currentCompound = f"{msgStyle['compoundSymbol'][tyreStint[-1]['Compound']]}{tyreStint[-1]['Compound']}"
    elif tyreStint:
        currentCompound = tyreStint[-1].get("Compound", "")

    # --- Event Handling ---
    # Handle Last Lap Time updates (fastest laps, personal bests).
    if (
        "LastLapTime" in delta
        and delta["LastLapTime"].get("Value")
    ):
        isOverallFastest = delta["LastLapTime"].get("OverallFastest") or timingDataF1["LastLapTime"].get("OverallFastest")
        isPersonalFastest = delta["LastLapTime"].get("PersonalFastest") or timingDataF1["LastLapTime"].get("PersonalFastest")

        if isOverallFastest:
            discord.post(
                username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
                embeds=[
                    {
                        "title": f"Quickest Overall - {delta['LastLapTime']['Value']}",
                        "fields": [
                            {
                                "name": "Sectors",
                                "value": "".join(
                                    (
                                        "\U0001f7ea"  # purple square
                                        if sector.get("OverallFastest")
                                        else (
                                            "\U0001f7e9"  # green square
                                            if sector.get("PersonalFastest")
                                            else "\U0001f7e8"  # yellow square
                                        )
                                    )
                                    for sector in timingDataF1["Sectors"]
                                ),
                                "inline": True,
                            },
                            {
                                "name": "Tyre",
                                "value": f"{currentCompound} (age: {tyreStint[-1]['TotalLaps']})" if tyreStint else "N/A",
                                "inline": True,
                            },
                        ],
                        "color": 10181046,  # Purple
                    },
                ],
                avatar_url=driverInfo.get("HeadshotUrl"),
            )
        elif isPersonalFastest and sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
            discord.post(
                username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
                embeds=[
                    {
                        "title": f"Personal Best - {delta['LastLapTime']['Value']}",
                        "fields": [
                            {
                                "name": "Sectors",
                                "value": "".join(
                                    (
                                        "\U0001f7ea"  # purple square
                                        if sector.get("OverallFastest")
                                        else (
                                            "\U0001f7e9"  # green square
                                            if sector.get("PersonalFastest")
                                            else "\U0001f7e8"  # yellow square
                                        )
                                    )
                                    for sector in timingDataF1["Sectors"]
                                ),
                                "inline": True,
                            },
                            {
                                "name": "Tyre",
                                "value": f"{currentCompound} (age: {tyreStint[-1]['TotalLaps']})" if tyreStint else "N/A",
                                "inline": True,
                            },
                        ],
                        "color": 5763719,  # Green
                    },
                ],
                avatar_url=driverInfo.get("HeadshotUrl"),
            )

    # Handle knocked out of qualifying.
    if delta.get("KnockedOut") and sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
        discord.post(
            username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
            embeds=[
                {
                    "title": f"Knocked Out - P{timingDataF1['Position']}",
                    "color": int(driverInfo["TeamColour"], 16),
                }
            ],
            avatar_url=driverInfo.get("HeadshotUrl"),
        )

    # Handle retirement.
    if delta.get("Retired"):
        lap_number = f" - Lap {timingDataF1.get('NumberOfLaps', 0) + 1}" if 'NumberOfLaps' in timingDataF1 else ''
        discord.post(
            username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
            embeds=[
                {
                    "title": f"Retired{lap_number}",
                    "color": int(driverInfo["TeamColour"], 16),
                }
            ],
            avatar_url=driverInfo.get("HeadshotUrl"),
        )

    # Handle race leader changes.
    if delta.get("Position") == "1" and sessionInfo["Type"] in ["Race", "Sprint"]:
        discord.post(
            username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
            embeds=[
                {
                    "title": f"Race Leader - {driverInfo['FullName']}",
                    "fields": [
                        {
                            "name": "TeamName",
                            "value": driverInfo["TeamName"],
                            "inline": True,
                        },
                    ],
                    "color": int(driverInfo["TeamColour"], 16),
                }
            ],
            avatar_url=driverInfo.get("HeadshotUrl"),
        )


async def connectRedisChannel() -> None:
    """
    Connects to the Redis server and subscribes to the TimingDataF1 channel.

    This function continuously listens for messages and calls the handler function.
    """
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("TimingDataF1")
        async for payload in pubsub.listen():
            if payload["type"] == "message":
                channel = payload["channel"].decode("utf-8")
                if channel == "TimingDataF1":
                    data = json.loads(payload["data"])
                    if "Lines" not in data or not isinstance(data["Lines"], dict):
                        continue
                    for raceNumber, delta in data["Lines"].items():
                        asyncio.create_task(
                            timingDataF1Handler(
                                redis_client,
                                Discord(url=DISCORD_WEBHOOK),
                                raceNumber,
                                delta,
                            )
                        )


if __name__ == "__main__":
    asyncio.run(connectRedisChannel())
