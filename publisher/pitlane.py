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

use_ssl = (os.getenv("USE_SSL", default="True")) == "True"
api_host = os.getenv("API_HOST", default="livetiming.formula1.com")
retry = (os.getenv("RETRY", default="True")) == "True"
msgStylePath = os.getenv("MSG_STYLE", default="")

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", default="redis")
REDIS_PORT = os.getenv("REDIS_PORT", default=6379) 
REDIS_CHANNEL = "RACE_CONTROL"

# livetimingUrl = f"https://{api_host}/signalr" if use_ssl == "true" else f"http://{api_host}/signalr"
livetimingUrl = urllib.parse.urljoin(
    f"https://{api_host}" if use_ssl else f"http://{api_host}", "/signalr"
)

# websocketUrl  = f"wss://{api_host}/signalr"   if use_ssl == "true" else f"ws://{api_host}/signalr"
websocketUrl = urllib.parse.urljoin(
    f"wss://{api_host}" if use_ssl else f"ws://{api_host}", "/signalr"
)

# staticUrl     = f"https://{api_host}/static"  if use_ssl == "true" else f"http://{api_host}/static"
staticUrl = urllib.parse.urljoin(
    f"https://{api_host}" if use_ssl else f"http://{api_host}", "/static"
)

clientProtocol = 1.5

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

async def connectRaceControl():
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
                                    "PitLaneTimeCollection",
                                    "PitStop", 
                                    "PitStopSeries",
                                ]
                            ],
                            "I": 1,
                        }
                    )
                )
                verbose = os.getenv("VERBOSE") == "True"
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
                                reference = redis_client.json().get(channel) 
                                reference = updateDictDelta(await reference, delta)
                                asyncio.create_task(redis_client.json().set(channel, Path.root_path(), reference))
                                # publish message
                                asyncio.create_task( redis_client.publish(channel, json.dumps(delta)) )

            except Exception as error:
                print(error)
                if retry:
                    continue
                else:
                    await redis_client.aclose()
                    break
            finally:
                await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(connectRaceControl())
