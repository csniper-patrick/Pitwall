# publisher/timing.py
"""
Connects to the F1 live timing websocket, processes timing data, and publishes
it to a Redis channel.

This script subscribes to the 'TimingDataF1' stream. It uses a debouncer to
batch 'LastLapTime' updates to avoid flooding consumers, while other timing data
is published immediately.
"""

import asyncio
import json
from typing import Optional

import redis.asyncio as redis
import websockets
from dotenv import load_dotenv
from redis.commands.json.path import Path

from utils import *

load_dotenv()

# --- Configuration ---
(
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
) = load_config()


class Debouncer:
    """
    A simple debouncer to delay publishing messages until a certain interval has passed.
    """

    def __init__(self, redis_client, channel, interval=3):
        """
        Initializes the Debouncer.

        Args:
            redis_client: An active Redis client instance.
            channel: The Redis channel to publish to.
            interval: The debounce interval in seconds.
        """
        self.interval = interval
        self.redis_client = redis_client
        self.channel = channel
        self.message = {}
        self.debounce_task = None

    async def add_message(self, message):
        """
        Adds a message to the debounce queue. If a task is already pending, it's cancelled.
        """
        self.message = updateDictDelta(self.message, message)
        if self.debounce_task:
            self.debounce_task.cancel()
        self.debounce_task = asyncio.create_task(self._delayed_publish())

    async def _delayed_publish(self):
        """Waits for the interval and then publishes the message."""
        try:
            await asyncio.sleep(self.interval)
            await self.redis_client.publish(self.channel, json.dumps(self.message))
            self.debounce_task = None
            self.message = {}
        except asyncio.CancelledError:
            # This is expected if a new message arrives before the interval is over.
            pass


async def connectLiveTiming(
    username: Optional[str] = None, password: Optional[str] = None
):
    """
    Connects to the live timing websocket, processes messages, and publishes them to Redis.
    """
    lastLapTimeDebouncer = {}
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )
    while True:
        # --- Negotiate Connection ---
        # Offload sync OAuth login and SignalR negotiation so the event loop stays responsive.
        data, headers, params, extra_headers = await asyncio.to_thread(
            negotiate_signalr, livetimingUrl, username=username, password=password
        )
        if not params:
            if RETRY:
                await asyncio.sleep(5)
                continue
            else:
                break

        # --- Connect to WebSocket ---
        try:
            async with websockets.connect(
                f"{websocketUrl}?{params}",
                additional_headers=extra_headers,
                ping_interval=None,
            ) as sock:
                # Complete SignalR Core JSON handshake and subscribe to TimingDataF1.
                initial_messages = await subscribe_signalr(sock, ["TimingDataF1"])

                # --- Message Processing Loop ---
                async for messages in iter_signalr_messages(sock, initial_messages):
                    if "R" in messages:
                        for key, value in messages["R"].items():
                            if isinstance(value, dict):
                                value.pop("_kf", None)
                            await redis_client.json().set(key, Path.root_path(), value)

                    if "M" in messages:
                        for msg in messages["M"]:
                            if msg["H"] == "Streaming":
                                channel, delta = msg["A"][0], msg["A"][1]
                                if isinstance(delta, dict):
                                    delta.pop("_kf", None)

                                if channel == "Heartbeat":
                                    continue

                                reference = await redis_client.json().get(channel)
                                reference = updateDictDelta(reference or {}, delta)
                                await redis_client.json().set(
                                    channel, Path.root_path(), reference
                                )

                                # --- Debounce LastLapTime Updates ---
                                # Extract LastLapTime from the delta to be debounced.
                                lastLapTimeDelta = {
                                    key: value.pop("LastLapTime", None)
                                    for key, value in delta.get("Lines", {}).items()
                                    if "LastLapTime" in value
                                }

                                if lastLapTimeDelta:
                                    for raceNumber, value in lastLapTimeDelta.items():
                                        if raceNumber not in lastLapTimeDebouncer:
                                            lastLapTimeDebouncer[raceNumber] = Debouncer(
                                                redis_client=redis_client, channel=channel
                                            )
                                        if value is not None:
                                            await lastLapTimeDebouncer[raceNumber].add_message(
                                                {
                                                    "Lines": {
                                                        raceNumber: {"LastLapTime": value}
                                                    }
                                                }
                                            )

                                # --- Publish Remaining Data Immediately ---
                                # Remove drivers with no more data in the delta.
                                if "Lines" in delta:
                                    delta["Lines"] = {
                                        key: value
                                        for key, value in delta["Lines"].items()
                                        if value
                                    }

                                # Publish the rest of the delta immediately.
                                if delta:
                                    asyncio.create_task(
                                        redis_client.publish(channel, json.dumps(delta))
                                    )

        except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError) as error:
            print(f"WebSocket connection error: {error}")
            if RETRY:
                await asyncio.sleep(5)
                continue
            else:
                break
        except Exception as error:
            print(f"An unexpected error occurred: {error}")
            if RETRY:
                await asyncio.sleep(5)
                continue
            else:
                break


if __name__ == "__main__":
    asyncio.run(connectLiveTiming())
