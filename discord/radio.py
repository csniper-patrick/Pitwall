import json
import asyncio
import redis.asyncio as redis
from dotenv import load_dotenv
from utils import *
from discordwebhook import Discord
from typing import *

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

async def radioCaptureHandler(redis_client: redis.Redis, discord: Discord, capture: Dict[str, Any]) -> None:
    # get data from redis
    sessionInfo = await redis_client.json().get("SessionInfo")
    driverInfo = (await redis_client.json().get("DriverList"))[capture['RacingNumber']]
    # if sessionInfo["Type"] not in ["Race", "Sprint"]:
    #     return
    if message := capture["Message"]:
        discord.post(
            username=f"{driverInfo['BroadcastName']} - {capture['RacingNumber']}{VER_TAG}",
            embeds=[
                {
                    "fields": [
                        {"name": "Team Radio", "value": message['text'], "inline": True},
                    ],
                    "color": int(driverInfo['TeamColour'], 16),
                }
            ],
            avatar_url=driverInfo["HeadshotUrl"] if "HeadshotUrl" in driverInfo else None
        )

async def connectRedisChannel() -> None:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
    # redis_client = redis.from_url(f"redis://{REDIS_HOST}")
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("TeamRadio")
        async for payload in pubsub.listen() :
            if payload["type"] == "message" :
                match payload["channel"].decode("utf-8"):
                    case "TeamRadio":
                        for capture in json.loads(payload["data"])["Captures"]:
                            asyncio.create_task(radioCaptureHandler(redis_client, Discord(url=DISCORD_WEBHOOK), capture))
                    case _ :
                        continue

if __name__ == "__main__":
    asyncio.run(connectRedisChannel())