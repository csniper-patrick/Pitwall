# publisher/radio.py
"""
Connects to the F1 live timing websocket, processes team radio messages, transcribes
the audio, and publishes the transcription to a Redis channel.

This script subscribes to the 'TeamRadio' data stream, downloads the audio files,
uses a local transformer model to transcribe them, and then publishes the result.
"""

import asyncio
import json
import os
from functools import reduce
from typing import Optional
from urllib.parse import urljoin

import redis.asyncio as redis
import websockets
import wget
from dotenv import load_dotenv
from redis.commands.json.path import Path
from transformers import pipeline

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

staticUrl = "https://livetiming.formula1.com/static/"

def negotiate(username: Optional[str] = None, password: Optional[str] = None):
    """
    Negotiates a connection with the SignalR Core server to get a connection ID
    and authenticated headers.

    Returns:
        A tuple containing the connection data, headers, URL parameters, and
        extra headers required for the WebSocket connection.
    """
    return negotiate_signalr(livetimingUrl, username=username, password=password)


async def captureHandler(redis_client, channel, transcriber, sessionInfo, capture):
    """
    Downloads, transcribes, and publishes a single team radio audio file.

    Args:
        redis_client: An active Redis client instance.
        channel: The Redis channel to publish to.
        transcriber: The Hugging Face pipeline for speech recognition.
        sessionInfo: The current session information.
        capture: The radio capture data, including the audio file path.
    """
    radioFile = None
    try:
        # Construct the full URL for the radio audio file.
        radioURL = reduce(urljoin, [staticUrl, sessionInfo["Path"], capture["Path"]])
        print(f"Downloading radio from: {radioURL}")
        radioFile = wget.download(radioURL)

        # Transcribe the audio file.
        print(f"Transcribing {radioFile}...")
        transcribe = transcriber(radioFile)
        capture["Message"] = transcribe

        # Publish the transcription to Redis.
        await redis_client.publish(channel, json.dumps({"Captures": [capture]}))
        print(f"Published transcription for {radioFile} to {channel}")

    except Exception as error:
        print(f"Error in captureHandler: {error}")
    finally:
        # Clean up the downloaded audio file.
        if radioFile and os.path.exists(radioFile):
            os.remove(radioFile)


async def connectLiveTiming(
    username: Optional[str] = None, password: Optional[str] = None
):
    """
    Connects to the live timing websocket, processes radio messages, and publishes them.
    """
    # --- Initialize Transcription Model ---
    model = os.getenv("WHISPERS_MODEL", default="distil-whisper/distil-medium.en")
    print(f"Loading transcription model: {model}")
    transcriber = pipeline("automatic-speech-recognition", model=model, return_timestamps=True)
    print("Transcription model loaded.")

    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True
    )

    while True:
        # --- Negotiate Connection ---
        # Offload sync OAuth login and SignalR negotiation so the event loop stays responsive.
        data, headers, params, extra_headers = await asyncio.to_thread(
            negotiate, username, password
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
                # Complete SignalR Core JSON handshake and subscribe to the TeamRadio stream.
                initial_messages = await subscribe_signalr(sock, ["TeamRadio"])

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

                                # Update the main TeamRadio data structure in Redis.
                                reference = await redis_client.json().get(channel)
                                sessionInfo = await redis_client.json().get("SessionInfo")
                                reference = updateDictDelta(reference or {}, delta)
                                await redis_client.json().set(
                                    channel, Path.root_path(), reference
                                )

                                # Process each new radio capture.
                                captures = delta.get("Captures", [])
                                if isinstance(captures, dict):
                                    captures = list(captures.values())

                                for capture in captures:
                                    asyncio.create_task(
                                        captureHandler(
                                            redis_client,
                                            channel,
                                            transcriber,
                                            sessionInfo,
                                            capture,
                                        )
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
