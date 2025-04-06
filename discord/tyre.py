import json
import asyncio
import redis.asyncio as redis
from dotenv import load_dotenv
from utils import *
from discordwebhook import Discord
from typing import *

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

async def tyresStintSeriesHandler(
    redis_client: redis.Redis,
    discord: Discord,
    raceNumber: str,
    delta: Dict[str, Any],
) -> None:
    # get data from redis
    sessionInfo = await redis_client.json().get("SessionInfo")
    timingDataF1 = (await redis_client.json().get("TimingDataF1"))["Lines"][raceNumber]
    driverInfo = (await redis_client.json().get("DriverList"))[raceNumber]
    tyreStint = (await redis_client.json().get("TyreStintSeries"))["Stints"][raceNumber]
    if sessionInfo["Type"] not in ["Race", "Sprint"]:
        return
    for idx, stint in delta.items():
        if "Compound" in stint:
            fullStintData = tyreStint[int(idx)]
            if stint['Compound'] in msgStyle["compoundSymbol"]:
                currentCompound = f"{msgStyle["compoundSymbol"][stint['Compound']]}{stint['Compound']}"
            else:
                currentCompound = stint['Compound']
            discord.post(
				username=f"{driverInfo['BroadcastName']} - {raceNumber}{VER_TAG}",
				embeds=[
					{
						"title": f"Tyre Change - { currentCompound }",
						"fields": [
							{"name": "Stint", "value": int(idx) + 1, "inline": True},
							{"name": "Age", "value": fullStintData["StartLaps"], "inline": True},
						],
						"color": msgStyle["compoundColor"][stint["Compound"]] if "Compound" in stint and stint["Compound"] in msgStyle["compoundColor"] else None,
					}
				],
				avatar_url=driverInfo["HeadshotUrl"] if "HeadshotUrl" in driverInfo else None
			)

async def connectRedisChannel() -> None:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
    # redis_client = redis.from_url(f"redis://{REDIS_HOST}")
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("TyreStintSeries", "Heartbeat")
        async for payload in pubsub.listen() :
            match payload["channel"].decode("utf-8"):
                case "TyreStintSeries":
                    if payload["type"] == "message" :
                        stints = json.loads(payload["data"])["Stints"]
                        for raceNumber, delta in stints.items():
                            if type(delta) == dict:
                                asyncio.create_task(tyresStintSeriesHandler(redis_client, Discord(url=DISCORD_WEBHOOK), raceNumber, delta))
                case _ :
                    continue
                    

if __name__ == "__main__":
    asyncio.run(connectRedisChannel())