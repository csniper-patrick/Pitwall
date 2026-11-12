# publisher/tyre.py
"""
Connects to the F1 live timing websocket, processes tyre-related data, and
publishes it to a Redis channel.

This script specifically subscribes to the 'TyreStintSeries' and 'CurrentTyres'
data streams.
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


def negotiate(username: Optional[str] = None, password: Optional[str] = None):
    """
    Negotiates a connection with the SignalR Core server to get a connection ID
    and authenticated headers.

    Returns:
        A tuple containing the connection data, headers, URL parameters, and
        extra headers required for the WebSocket connection.
    """
    return negotiate_signalr(livetimingUrl, username=username, password=password)


async def connectLiveTiming(
    username: Optional[str] = None, password: Optional[str] = None
):
    """
    Connects to the live timing websocket, processes messages, and publishes them to Redis.
    """
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )
    while True:
        # --- Negotiate Connection ---
        data, headers, params, extra_headers = await asyncio.to_thread(
            negotiate, username, password
        )
        if not params:
            if RETRY:
                await asyncio.sleep(5)  # Wait before retrying
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
                # Subscribe to the required data streams.
                initial_messages = await subscribe_signalr(
                    sock, ["TyreStintSeries", "CurrentTyres"]
                )

                # --- Message Processing Loop ---
                async for messages in iter_signalr_messages(sock, initial_messages):
                    # Handle full data structure updates.
                    if "R" in messages:
                        for key, value in messages["R"].items():
                            if isinstance(value, dict):
                                value.pop("_kf", None)
                            await redis_client.json().set(key, Path.root_path(), value)

                    # Handle delta updates.
                    if "M" in messages:
                        for msg in messages["M"]:
                            if msg["H"] == "Streaming":
                                channel, delta = msg["A"][0], msg["A"][1]
                                if isinstance(delta, dict):
                                    delta.pop("_kf", None)

                                if channel == "Heartbeat":
                                    continue

                                # Get the existing data from Redis and apply the delta.
                                reference = await redis_client.json().get(channel)
                                reference = updateDictDelta(reference or {}, delta)

                                # Save the updated data back to Redis.
                                await redis_client.json().set(
                                    channel, Path.root_path(), reference
                                )
                                # Publish the delta to the Redis channel for consumers.
                                asyncio.create_task(
                                    redis_client.publish(channel, json.dumps(delta))
                                )

        except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError) as error:
            print(f"WebSocket connection error: {error}")
            if RETRY:
                await asyncio.sleep(5) # Wait before retrying
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
