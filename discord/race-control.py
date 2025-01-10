import requests
import json
import asyncio
import os
import redis.asyncio as redis
from redis.commands.json.path import Path
from dotenv import load_dotenv
from utils import *

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, RACE_DIRECTOR, MSG_STYLE, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

async def raceControlMessageHandler(messages):
    print(json.dumps(messages, indent=2))


async def connectRedisChannel():
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    # redis_client = redis.from_url(f"redis://{REDIS_HOST}")
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("RaceControlMessages")
        async for payload in pubsub.listen() :
            if payload["type"] == "message" :
                asyncio.create_task(raceControlMessageHandler(json.loads(payload["data"])))

if __name__ == "__main__":
    asyncio.run(connectRedisChannel())