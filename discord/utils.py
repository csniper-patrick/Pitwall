import os
import json

def load_config():
    
    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
    VER_TAG = os.getenv("VER_TAG", default="")
    RACE_DIRECTOR = os.getenv("RACE_DIRECTOR", default="Race Director")
    MSG_STYLE = os.getenv("MSG_STYLE", default="")
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
    }
    if os.path.isfile(MSG_STYLE):
        with open(MSG_STYLE) as f:
            msgStyle = updateDictDelta(msgStyle, json.load(f))

    # Redis configuration
    REDIS_HOST = os.getenv("REDIS_HOST", default="redis")
    REDIS_PORT = os.getenv("REDIS_PORT", default=6379) 
    REDIS_CHANNEL = "RACE_CONTROL"

    RETRY = (os.getenv("RETRY", default="True")) == "True"

    return DISCORD_WEBHOOK, VER_TAG, RACE_DIRECTOR, msgStyle, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY
