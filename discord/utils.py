import os

def load_config():
    
    DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
    VER_TAG = os.getenv("VER_TAG", default="")
    RACE_DIRECTOR = os.getenv("RACE_DIRECTOR", default="Race Director")
    MSG_STYLE = os.getenv("MSG_STYLE", default="")

    # Redis configuration
    REDIS_HOST = os.getenv("REDIS_HOST", default="redis")
    REDIS_PORT = os.getenv("REDIS_PORT", default=6379) 
    REDIS_CHANNEL = "RACE_CONTROL"

    RETRY = (os.getenv("RETRY", default="True")) == "True"

    return DISCORD_WEBHOOK, VER_TAG, RACE_DIRECTOR, MSG_STYLE, REDIS_HOST, REDIS_PORT, REDIS_CHANNEL, RETRY