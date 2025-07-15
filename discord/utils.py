import os
import json
from typing import *


def updateDictDelta(obj: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
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


def load_config() -> Tuple[str, str, Dict[str, Any], str, int, str, bool]:

    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
    VER_TAG = os.getenv("VER_TAG", default="")
    MSG_STYLE_PATH = os.getenv("MSG_STYLE_PATH", default="./style.json")
    msgStyle = {
        "flagColor": {
            "GREEN": 5763719,
            "CLEAR": 5763719,
            "YELLOW": 16776960,
            "DOUBLE YELLOW": 16776960,
            "CHEQUERED": 16777215,
            "BLUE": 3447003,
            "RED": 15548997,
            "BLACK AND WHITE": 16777215,
            "BLACK AND ORANGE": 15105570,
            "BLACK": 2303786,
        },
        "flagSymbol": {"CHEQUERED": ":checkered_flag:", "BLACK": ":flag_black:"},
        "modeColor": {"SAFETY CAR": 15844367, "VIRTUAL SAFETY CAR": 15844367},
        "compoundColor": {
            "SOFT": 15548997,  # RED
            "MEDIUM": 16776960,  # YELLOW
            "HARD": 16777215,  # WHITE
            "INTERMEDIATE": 2067276,  # GREEN
            "WET": 2123412,  # BLUE
        },
        "compoundSymbol": {},
        "raceDirector": "Race Director",
    }
    if os.path.isfile(MSG_STYLE_PATH):
        with open(MSG_STYLE_PATH) as f:
            msgStyle = updateDictDelta(msgStyle, json.load(f))

    # Redis configuration
    REDIS_HOST = os.getenv("REDIS_HOST", default="redis")
    REDIS_PORT = os.getenv("REDIS_PORT", default=6379)
    REDIS_CHANNEL = "RACE_CONTROL"

    RETRY = (os.getenv("RETRY", default="True")) == "True"

    return DISCORD_WEBHOOK, VER_TAG, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY
