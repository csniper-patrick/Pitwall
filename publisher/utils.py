import re
import os
from dotenv import load_dotenv
import urllib.parse

def updateDictDelta(obj, delta):
    for key, value in delta.items():
        if key not in obj:
            obj[key] = value
        elif type(value) == dict and type(obj[key]) == dict:
            obj[key] = updateDictDelta(obj[key], value)
        elif (
            type(value) == dict
            and type(obj[key]) == list
            and all([k.isnumeric() for k in value.keys()])
        ):
            tempDict = dict([(str(idx), value) for idx, value in enumerate(obj[key])])
            tempDict = updateDictDelta(tempDict, value)
            obj[key] = [value for _, value in tempDict.items()]
        else:
            obj[key] = value
    return obj


def timeStr2msec(timeStr: str):
    return (
        sum(
            [
                val * scaler
                for val, scaler in zip(
                    reversed([float(i) for i in re.split(":", timeStr)]), [1, 60]
                )
            ]
        )
        * 1000
    )


def msec2timeStr(msec: int, signed: bool = False):
    val = int(abs(msec))
    if signed:
        timeStr = "+" if msec >= 0 else "-"
    else:
        timeStr = "" if msec >= 0 else "-"
    if val >= 60000:
        timeStr += str(val // 60000) + ":"
        val %= 60000
    timeStr += str(val // 1000)
    timeStr += "." + str(val % 1000).zfill(3)
    return timeStr

def load_config():

    use_ssl = (os.getenv("USE_SSL", default="True")) == "True"
    api_host = os.getenv("API_HOST", default="livetiming.formula1.com")
    retry = (os.getenv("RETRY", default="True")) == "True"

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

    # Redis configuration
    REDIS_HOST = os.getenv("REDIS_HOST", default="redis")
    REDIS_PORT = os.getenv("REDIS_PORT", default=6379) 
    REDIS_CHANNEL = "RACE_CONTROL"

    clientProtocol = 1.5

    return use_ssl, api_host, retry, livetimingUrl, websocketUrl, staticUrl, clientProtocol, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL
