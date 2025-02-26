import requests
import json
import asyncio
import websockets
import urllib.parse
import os
from dotenv import load_dotenv
import redis.asyncio as redis
from redis.commands.json.path import Path
from utils import *

load_dotenv()

USE_SSL, API_HOST, RETRY, livetimingUrl, websocketUrl, staticUrl, clientProtocol, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL = load_config()

def negotiate():
    connectionData = [{"name": "Streaming"}]
    try:
        res = requests.get(
            f"{livetimingUrl}/negotiate",
            params={
                "connectionData": json.dumps(connectionData),
                "clientProtocol": clientProtocol,
            },
        )
        print(res.json(), res.headers)
        return res.json(), res.headers, urllib.parse.urlencode(
            {
                "clientProtocol": 1.5,
                "transport": "webSockets",
                "connectionToken": res.json()["ConnectionToken"],
                "connectionData": json.dumps([{"name": "Streaming"}]),
            }
        ), {
            "User-Agent": "BestHTTP",
            "Accept-Encoding": "gzip,identity",
            "Cookie": res.headers["Set-Cookie"],
        }
        
    except:
        print("error")

async def connectLiveTiming():
    while True:
        data, headers, params, additional_headers = negotiate()
        
		# connect to redis 
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
        async with websockets.connect(
            f"{websocketUrl}/connect?{params}",
            additional_headers=additional_headers,
            ping_interval=None,
        ) as sock:
            try:
                await sock.send(
                    json.dumps(
                        {
                            "H": "Streaming",
                            "M": "Subscribe",
                            "A": [
                                [
                                    "Heartbeat",
                                    "PitLaneTimeCollection",
                                    "PitStop", 
                                    "PitStopSeries",
                                ]
                            ],
                            "I": 1,
                        }
                    )
                )
                while messages := json.loads(await sock.recv()):
                    # update data structure (full)
                    if "R" in messages:
                        for key, value in messages["R"].items():
                            await redis_client.json().set(key, Path.root_path(), value)
                    # update data structure (delta)
                    if "M" in messages:
                        for msg in messages["M"]:
                            if msg["H"] == "Streaming":
                                channel, delta = msg["A"][0],  msg["A"][1]
                                if channel == "Heartbeat":
                                    continue
                                reference = await redis_client.json().get(channel)
                                match channel:
                                    case  "PitLaneTimeCollection":
                                        if deleted := delta["PitTimes"].pop("_deleted", None) :
                                            for key in deleted:
                                                reference["PitTimes"].pop(key, None)
                                reference = updateDictDelta(reference, delta)
                                asyncio.create_task(redis_client.json().set(channel, Path.root_path(), reference))
                                # publish message
                                asyncio.create_task( redis_client.publish(channel, json.dumps(delta)) )

            except Exception as error:
                print(error)
                if RETRY:
                    continue
                else:
                    await redis_client.aclose()
                    break
            finally:
                await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(connectLiveTiming())
