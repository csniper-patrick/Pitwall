import json
import asyncio
import redis.asyncio as redis
from dotenv import load_dotenv
from utils import *
from discordwebhook import Discord

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

async def timingDataF1Handler(redis_client, discord, raceNumber, delta):
    # get data from redis
    sessionInfo = await redis_client.json().get("SessionInfo")
    timingDataF1 = (await redis_client.json().get("TimingDataF1"))["Lines"][raceNumber]
    driverInfo = (await redis_client.json().get("DriverList"))[raceNumber]
    tyreStint = (await redis_client.json().get("TyreStintSeries"))["Stints"][raceNumber]

    if len(tyreStint)>0 and tyreStint[-1]["Compound"] in msgStyle["compoundSymbol"]:
        currentCompound = f"{msgStyle["compoundSymbol"][tyreStint[-1]["Compound"]]}{tyreStint[-1]["Compound"]}"
    elif len(tyreStint)>0 :
        currentCompound = tyreStint[-1]["Compound"]
    
    # Handle Last Lap Time update
    if "LastLapTime" in delta and "Value" in delta["LastLapTime"] and delta["LastLapTime"]["Value"] != "":
        isOverallFastest = ('OverallFastest' in delta["LastLapTime"] and delta["LastLapTime"]["OverallFastest"]) or ('OverallFastest' not in delta["LastLapTime"] and timingDataF1["LastLapTime"]["OverallFastest"])
        isPersonalFastest=('PersonalFastest' in delta["LastLapTime"] and delta["LastLapTime"]["PersonalFastest"]) or ('PersonalFastest' not in delta["LastLapTime"] and timingDataF1["LastLapTime"]["PersonalFastest"])
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
                                    map(
                                        lambda sector: (
                                            "\U0001F7EA" # purple square emoji
                                            if sector["OverallFastest"]
                                            else (
                                                "\U0001F7E9" # green square emoji
                                                if sector["PersonalFastest"]
                                                else "\U0001F7E8" # yellow square emoji
                                            )
                                        ),
                                        timingDataF1["Sectors"],
                                    )
                                ),
                                "inline": True
                            },
                            {
                                "name": "Tyre",
                                "value": f"{currentCompound} (age: {tyreStint[-1]["TotalLaps"]})",
                                "inline": True
                            },
                        ],
                        "color": 10181046 #Purple
                    },
                ],
                avatar_url=driverInfo["HeadshotUrl"] if "HeadshotUrl" in driverInfo else None
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
                                    map(
                                        lambda sector: (
                                            "\U0001F7EA" # purple square emoji
                                            if sector["OverallFastest"]
                                            else (
                                                "\U0001F7E9" # green square emoji
                                                if sector["PersonalFastest"]
                                                else "\U0001F7E8" # yellow square emoji
                                            )
                                        ),
                                        timingDataF1["Sectors"],
                                    )
                                ),
                                "inline": True
                            },
                            {
                                "name": "Tyre",
                                "value": f"{currentCompound} (age: {tyreStint[-1]["TotalLaps"]})",
                                "inline": True
                            },
                        ],
                        "color": 5763719 #Green
                    },
                ],
                avatar_url=driverInfo["HeadshotUrl"] if "HeadshotUrl" in driverInfo else None
            )
    # Handle knocked out of qualifying
    if "KnockedOut" in delta and delta["KnockedOut"] and sessionInfo["Type"] in ["Qualifying", "Sprint Shootout"]:
        discord.post(
            username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
            embeds=[
                {
                    "title": f"Knocked Out - P{timingDataF1['Position']}",
                    "color": int(driverInfo['TeamColour'], 16),
                }
            ],
            avatar_url=driverInfo["HeadshotUrl"] if "HeadshotUrl" in driverInfo else None
        )
    # Handle retirement
    if "Retired" in delta and delta["Retired"]:
        discord.post(
            username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
            embeds=[
                {
                    "title": f"Retired{ (' - Lap ' + str(timingDataF1['NumberOfLaps'] + 1) )if 'NumberOfLaps' in timingDataF1 else '' }",
                    "color": int(driverInfo['TeamColour'], 16),
                }
            ],
            avatar_url=driverInfo["HeadshotUrl"] if "HeadshotUrl" in driverInfo else None
        )
    # Race Leader
    if "Position" in delta and delta["Position"] == "1" and sessionInfo["Type"] in ["Race", "Sprint"]:
        discord.post(
            username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
            embeds=[
                {
                    "title": f"Race Leader - {driverInfo['FullName']}",
                    "fields": [
                        {"name": "TeamName", "value": driverInfo["TeamName"], "inline": True},
                    ],
                    "color": int(driverInfo['TeamColour'], 16),
                }
            ],
            avatar_url=driverInfo["HeadshotUrl"] if "HeadshotUrl" in driverInfo else None
        )



async def connectRedisChannel():
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
    # redis_client = redis.from_url(f"redis://{REDIS_HOST}")
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("TimingDataF1", "Heartbeat")
        async for payload in pubsub.listen() :
            if payload["type"] == "message" :
                match payload["channel"].decode("utf-8"):
                    case "TimingDataF1":
                        data = json.loads(payload["data"])
                        if "Lines" not in data:
                            continue
                        if type(data["Lines"])== dict:
                            for raceNumber, delta in data["Lines"].items():
                                asyncio.create_task(timingDataF1Handler(redis_client, Discord(url=DISCORD_WEBHOOK), raceNumber, delta))
                    case _ :
                        continue

if __name__ == "__main__":
    asyncio.run(connectRedisChannel())