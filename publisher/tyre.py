# publisher/tyre.py
"""
Connects to the F1 live timing websocket, processes tyre-related data, and
publishes it to a Redis channel.

This script specifically subscribes to the 'TyreStintSeries' and 'CurrentTyres'
data streams.
"""

import asyncio
import json
import os
import urllib.parse

import redis.asyncio as redis
import requests
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


def negotiate():
    """
    Negotiates a connection with the SignalR server to get a connection token.

    Returns:
        A tuple containing the connection data, headers, URL parameters, and
        extra headers required for the WebSocket connection.
    """
    connectionData = [{"name": "Streaming"}]
    try:
        # Get a connection token from the SignalR server.
        res = requests.get(
            f"{livetimingUrl}/negotiate",
            params={
                "connectionData": json.dumps(connectionData),
                "clientProtocol": clientProtocol,
            },
        )
        res.raise_for_status()  # Raise an exception for bad status codes
        data = res.json()

        # Construct the WebSocket URL parameters.
        params = urllib.parse.urlencode(
            {
                "clientProtocol": clientProtocol,
                "transport": "webSockets",
                "connectionToken": data["ConnectionToken"],
                "connectionData": json.dumps(connectionData),
            }
        )

        # Set the necessary headers for the WebSocket connection.
        extra_headers = {
            "User-Agent": "BestHTTP",
            "Accept-Encoding": "gzip,identity",
            "Cookie": res.headers.get("Set-Cookie", ""),
        }

        return data, res.headers, params, extra_headers

    except requests.exceptions.RequestException as error:
        print(f"Negotiation failed: {error}")
        return None, None, None, None


async def connectLiveTiming():
    """
    Connects to the live timing websocket, processes messages, and publishes them to Redis.
    """
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )
    while True:
        # --- Negotiate Connection ---
        data, headers, params, extra_headers = negotiate()
        if not params:
            if RETRY:
                await asyncio.sleep(5)  # Wait before retrying
                continue
            else:
                break

        # --- Connect to WebSocket ---
        try:
            async with websockets.connect(
                f"{websocketUrl}/connect?{params}",
                additional_headers=extra_headers,
                ping_interval=None,
            ) as sock:
                # Subscribe to the required data streams.
                await sock.send(
                    json.dumps(
                        {
                            "H": "Streaming",
                            "M": "Subscribe",
                            "A": [["TyreStintSeries", "CurrentTyres"]],
                            "I": 1,
                        }
                    )
                )

                # --- Message Processing Loop ---
                while True:
                    messages = json.loads(await sock.recv())

                    # Handle full data structure updates.
                    if "R" in messages:
                        for key, value in messages["R"].items():
                            value.pop("_kf", None)
                            await redis_client.json().set(key, Path.root_path(), value)

                    # Handle delta updates.
                    if "M" in messages:
                        for msg in messages["M"]:
                            if msg["H"] == "Streaming":
                                channel, delta = msg["A"][0], msg["A"][1]
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
