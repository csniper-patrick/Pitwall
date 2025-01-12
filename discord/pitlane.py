import json
import asyncio
import redis.asyncio as redis
from dotenv import load_dotenv
from utils import *
from discordwebhook import Discord
from collections import defaultdict
import re

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, RACE_DIRECTOR, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

# load pit time reference
pit_time_reference=defaultdict(lambda: dict(mean=25., std=5.))
with open('data/pit-time-stat.json', 'r') as file:
    for circuit, stat in json.load(file).items():
        pit_time_reference[circuit]['mean']=stat["mean"]
        pit_time_reference[circuit]['std']=stat["std"]

async def pitLaneTimeCollectionHandler(redis_client, discord, raceNumber, delta):
    # get data from redis
    if "RacingNumber" not in delta or raceNumber != delta["RacingNumber"]:
        return
    sessionInfo = await redis_client.json().get("SessionInfo")
    if sessionInfo["Type"] not in ["Race", "Sprint"]:
        return
    driverInfo = (await redis_client.json().get("DriverList"))[raceNumber]
    durationSec = reversed(
        [float(i) for i in re.split(":", delta["Duration"])]
    )
    durationSec = sum([val * scaler for val, scaler in zip(durationSec, [1, 60])])
    circuit=sessionInfo['Meeting']['Circuit']['ShortName']
    z_score_1 = pit_time_reference[circuit]['mean']+pit_time_reference[circuit]['std']
    if durationSec >= z_score_1 and durationSec <= 600.0:
        discord.post(
            username=f"{driverInfo['TeamName']}{VER_TAG}",
            embeds=[
                {
                    "title": f"Slow Pit Stop - {delta["Duration"]} in pit lane",
                    "fields": [
                        {
                            "name": "Driver",
                            "value": driverInfo["FullName"],
                            "inline": True,
                        },
                    ],
                    "color": int(driverInfo["TeamColour"], 16),
                }
            ],
        )

async def pitStopHandler(redis_client, discord, message):
    sessionInfo = await redis_client.json().get("SessionInfo")
    if sessionInfo["Type"] not in ["Race", "Sprint"]:
        return
    driverInfo = (await redis_client.json().get("DriverList"))[message["RacingNumber"]]
    discord.post(
        username=f"{driverInfo['TeamName']}{VER_TAG}",
        embeds=[
            {
                "title": f"Pit Stop - {message["PitStopTime"]}",
                "fields": [
                    {
                        "name": "Driver",
                        "value": driverInfo["FullName"],
                        "inline": True,
                    },
                ],
                "color": int(driverInfo["TeamColour"], 16),
            }
        ],
    )
    return

async def connectRedisChannel():
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    discord = Discord(url=DISCORD_WEBHOOK)
    # redis_client = redis.from_url(f"redis://{REDIS_HOST}")
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("PitLaneTimeCollection", "PitStop", "PitStopSeries")
        async for payload in pubsub.listen() :
            if payload["type"] == "message" :
                match payload["channel"].decode("utf-8"):
                    case "PitLaneTimeCollection":
                        pitTimes=json.loads(payload["data"])["PitTimes"]
                        for raceNumber, delta in pitTimes.items():
                            asyncio.create_task(pitLaneTimeCollectionHandler(redis_client, discord, raceNumber, delta))
                    case "PitStop":
                        pitStop=json.loads(payload["data"])
                        asyncio.create_task(pitStopHandler(redis_client, discord, pitStop))
                    case _ :
                        continue
                    

if __name__ == "__main__":
    asyncio.run(connectRedisChannel())