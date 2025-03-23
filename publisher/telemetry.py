import requests
import json
import asyncio
import websockets
import urllib.parse
import os
from dotenv import load_dotenv
import redis.asyncio as redis
from redis.commands.json.path import Path
import base64
import zlib
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
        
    except Exception as error:
        print(error)

async def connectLiveTiming():
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    while True:
        data, headers, params, additional_headers = negotiate()
        
		# connect to redis 
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
                                    "Position.z",
                                    "CarData.z",
                                ]
                            ],
                            "I": 1,
                        }
                    )
                )
                while messages := json.loads(await sock.recv()):
                    # update data structure (full)
                    if "R" in messages:
                        for key, value_zip in messages["R"].items():
                            value = json.loads(zlib.decompress(base64.b64decode(value_zip), -zlib.MAX_WBITS))
                            await redis_client.json().set(key.replace(".z",''), Path.root_path(), value)
                    # update data structure (delta)
                    if "M" in messages:
                        for msg in messages["M"]:
                            if msg["H"] == "Streaming":
                                channel, value_zip = msg["A"][0].replace(".z",''),  msg["A"][1]
                                value = json.loads(zlib.decompress(base64.b64decode(value_zip), -zlib.MAX_WBITS))
                                asyncio.create_task(redis_client.json().set(channel, Path.root_path(), value))
                                asyncio.create_task(redis_client.publish(channel, json.dumps(value)))

            except Exception as error:
                print(error)
                if RETRY:
                    continue
                else:
                    break
                

if __name__ == "__main__":
    asyncio.run(connectLiveTiming())
