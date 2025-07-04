import json
import asyncio
import redis.asyncio as redis
from dotenv import load_dotenv
from utils import *
from discordwebhook import Discord
from typing import *

load_dotenv()

DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY = load_config()

async def raceControlMessageHandler(redis_client: redis.Redis, discord: Discord, messages: Dict[str, Any]) -> None:
    flagColor = msgStyle["flagColor"]
    flagSymbol = msgStyle["flagSymbol"]
    modeColor = msgStyle["modeColor"]
    if type( messages["Messages"] ) == dict :
        messages["Messages"] = [ value for _, value in messages["Messages"].items() ]
    for content in messages["Messages"]:
        if "Flag" in content and content["Flag"] == "BLUE":
            continue
        if "Flag" in content and content["Flag"] in flagSymbol:
            content["Message"] = f"{flagSymbol[content['Flag']]}{content['Message']}"
        discord.post(
            username=f"{msgStyle["raceDirector"]}{VER_TAG}",
            embeds=[
                {
                    "title": content["Message"],
                    "fields": [
                        {"name": key, "value": value, "inline": True}
                        for key, value in content.items()
                        if key in ["Mode", "Status"]
                    ],
                    "color": (
                        flagColor[content["Flag"]]
                        if "Flag" in content and content["Flag"] in flagColor
                        else (
                            modeColor[content["Mode"]]
                            if "Mode" in content and content["Mode"]
                            else None
                        )
                    ),
                }
            ],
        )

async def connectRedisChannel() -> None:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_keepalive=True)
    # redis_client = redis.from_url(f"redis://{REDIS_HOST}")
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe("RaceControlMessages")
        async for payload in pubsub.listen() :
            if payload["type"] == "message" :
                match payload["channel"].decode("utf-8"):
                    case "RaceControlMessages":
                        asyncio.create_task(raceControlMessageHandler(redis_client, Discord(url=DISCORD_WEBHOOK), json.loads(payload["data"])))
                    case _ :
                        continue

if __name__ == "__main__":
    asyncio.run(connectRedisChannel())