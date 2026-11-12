# publisher/telemetry.py
"""
Connects to the F1 live timing websocket, processes compressed telemetry data, and
publishes it to a Redis channel.

This script subscribes to the 'Position.z' and 'CarData.z' data streams, which
contain zlib-compressed, base64-encoded JSON data.
"""

import asyncio
import base64
import json
import zlib
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
        # Offload sync OAuth login and SignalR negotiation so the event loop stays responsive.
        data, headers, params, extra_headers = await asyncio.to_thread(
            negotiate_signalr, livetimingUrl, username=username, password=password
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
                # Complete SignalR Core JSON handshake and subscribe to compressed streams.
                initial_messages = await subscribe_signalr(
                    sock, ["Position.z", "CarData.z"]
                )

                # --- Message Processing Loop ---
                async for messages in iter_signalr_messages(sock, initial_messages):
                    # Handle full data structure updates.
                    if "R" in messages:
                        for key, value_zip in messages["R"].items():
                            # Decompress the zlib-compressed, base64-encoded data.
                            value = json.loads(
                                zlib.decompress(base64.b64decode(value_zip), -zlib.MAX_WBITS)
                            )
                            value.pop("_kf", None)
                            # Store the decompressed data in Redis.
                            await redis_client.json().set(
                                key.replace(".z", ""), Path.root_path(), value
                            )

                    # Handle delta updates.
                    if "M" in messages:
                        for msg in messages["M"]:
                            if msg["H"] == "Streaming":
                                channel, value_zip = (
                                    msg["A"][0].replace(".z", ""),
                                    msg["A"][1],
                                )
                                # Decompress the delta update.
                                value = json.loads(
                                    zlib.decompress(base64.b64decode(value_zip), -zlib.MAX_WBITS)
                                )
                                value.pop("_kf", None)

                                # Store the updated data in Redis.
                                await redis_client.json().set(
                                    channel, Path.root_path(), value
                                )

                                # Publish the decompressed data to the Redis channel.
                                asyncio.create_task(
                                    redis_client.publish(channel, json.dumps(value))
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
