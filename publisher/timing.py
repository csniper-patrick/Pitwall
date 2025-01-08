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
        data, headers, params, extra_headers = negotiate()
        
		# connect to redis 
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
        async with websockets.connect(
            f"{websocketUrl}/connect?{params}",
            extra_headers=extra_headers,
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
                                    "TimingDataF1"
                                ]
                            ],
                            "I": 1,
                        }
                    )
                )
                verbose = os.getenv("VERBOSE") == "True"
                while messages := await sock.recv():
                    messages = json.loads(messages)
                    # update data structure (full)
                    if "R" in messages:
                        for key, value in messages["R"].items():
                            await redis_client.json().set(key, Path.root_path(), value)
                    # update data structure (delta)
                    if "M" in messages:
                        for msg in messages["M"]:
                            if msg["H"] == "Streaming":
                                reference = await redis_client.json().get(msg["A"][0]) 
                                reference = updateDictDelta(reference, msg["A"][1])
                                await redis_client.json().set(msg["A"][0], Path.root_path(), reference)
                                # publish message
                                await redis_client.publish(msg["A"][0], json.dumps(msg["A"][1]))

            except Exception as error:
                print(error)
                if retry:
                    continue
                else:
                    break

if __name__ == "__main__":
    asyncio.run(connectRaceControl())
