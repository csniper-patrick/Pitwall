import json
import asyncio
import redis.asyncio as redis
from dotenv import load_dotenv
from utils import *
from discordwebhook import Discord

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

async def radioCaptureHandler(redis_client, discord, capture):
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
                    "title": "Team Radio",
                    "fields": [
                        {"name": "Message", "value": message['text'], "inline": True},
                    ],
                    "color": int(driverInfo['TeamColour'], 16),
                }
            ],
            avatar_url=driverInfo["HeadshotUrl"] if "HeadshotUrl" in driverInfo else None
        )

async def connectRedisChannel():
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    discord = Discord(url=DISCORD_WEBHOOK)
    # redis_client = redis.from_url(f"redis://{REDIS_HOST}")
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("TeamRadio")
        async for payload in pubsub.listen() :
            if payload["type"] == "message" :
                for capture in json.loads(payload["data"])["Captures"]:
                    asyncio.create_task(radioCaptureHandler(redis_client, discord, capture))
                    

if __name__ == "__main__":
    asyncio.run(connectRedisChannel())