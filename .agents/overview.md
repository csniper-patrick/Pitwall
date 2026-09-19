# System Overview & Architecture

## 1. Project Overview

**Pitwall** is a Python-based Discord bot for Formula 1 fans. It connects to the live F1 timing data feeds, publishes structured data to a Redis broker, and consumes this data to push real-time updates and handle interactive on-demand slash commands.

The project is structured as a decoupled microservice architecture:
1. **Publisher Services (`publisher/`)**: Connect to the live timing WebSocket endpoints (SignalR), retrieve JSON payloads, apply deltas to the master Redis JSON store, and publish updates to dedicated Redis channels.
2. **Redis Broker (`redis-stack`)**: Serves as a low-latency data store (using RedisJSON) and pub/sub message broker.
3. **Discord Services (`discord/`)**: Listen to Redis pub/sub channels, format data into Discord embeds using webhooks/web-requests, and run a Discord bot client to handle slash commands.
4. **Mock API (`mock-api/`)**: Simulates the F1 live timing SignalR and HTTP endpoints by replaying historical event streams (from static archives). It is used for local development and testing.

```
                  +--------------------------+
                  |  Formula 1 Live Timing   |
                  |     (Websocket/HTTP)     |
                  +-------------+------------+
                                |
                                v
                  +--------------------------+
                  |    Publisher Services    | (publisher/race-control.py,
                  |       (Python/WS)        |  timing.py, pitlane.py, etc.)
                  +-------------+------------+
                                | (publish updates & save state)
                                v
                  +--------------------------+
                  |    Redis Stack (DB 0)    | (holds JSON state,
                  |    (JSON & Pub/Sub)      |  broadcasts delta updates)
                  +-------+--------------+---+
                          |              |
         (sub to channel) |              | (query live timing data)
                          v              v
            +-------------+---+      +---+-------------------------+
            |  Discord Push   |      |  Discord Bot (slash cmds)   |
            |  (discord/*.py) |      | (discord/command.py/groups) |
            +-------------+---+      +---+-------------------------+
                          |              |
                          +------+-------+
                                 |
                                 v
                        +-----------------+
                        |  Discord Guild  |
                        +-----------------+
```

---

## 2. Directory Layout & Key Files

*   `publisher/`: Services subscribing to SignalR streams.
    *   `publisher/utils.py`: Shared functions for SignalR connection negotiation, timing formats (`timeStr2msec`, `msec2timeStr`), and configuration loading.
    *   `publisher/*.py`: Specific publisher tasks (e.g., `race-control.py`, `timing.py`, `pitlane.py`, `tyre.py`, `telemetry.py`, `radio.py`).
*   `discord/`: Services listening to Redis pub/sub or handling commands.
    *   `discord/utils.py`: Shared functions for styling (parsing `style.json` / default styling dictionary) and configuration.
    *   `discord/command.py`: Main slash command bot executable. Uses command groups defined in `race_engineer_group.py` and `strategist_group.py`.
    *   `discord/race_engineer_group.py`: Slash commands querying live data from Redis (e.g. tyres, gaps).
    *   `discord/strategist_group.py`: Slash commands querying archived data using the `FastF1` library.
    *   `discord/*.py`: Consumers formatting Redis streams into Discord webhook embeds.
*   `mock-api/`: Replays static live timing JSON files for offline development.
*   `compose.yaml` / `compose.dev.yaml`: Production and development multi-container orchestration.

---

## 3. Configuration & Environment Variables

Configure settings through environment files. Examples are available in `*.env.example`.

### Publisher Configuration (`publish.env` / `publish-dev.env`)
*   `REDIS_HOST` (default: `redis`): Hostname of Redis instance.
*   `REDIS_PORT` (default: `6379`): Port of Redis instance.
*   `RETRY` (default: `True`): Auto-reconnect to Live Timing & Redis on error.
*   `API_HOST` (default: `livetiming.formula1.com`): SignalR/API server (modified to `proxy` in dev mode).
*   `USE_SSL` (default: `True`): Use SSL for API connection (disabled in dev mode).

### Discord Bot Configuration (`discord.env` / `discord-dev.env`)
*   `DISCORD_BOT_TOKEN`: Required for the slash command bot client.
*   `DISCORD_WEBHOOK`: Webhook URL used to post live push notifications.
*   `MSG_STYLE_PATH` (default: `./style.json`): Path to JSON overriding symbols/colors.
*   `VER_TAG`: Appended to bot messages.
*   `LOG_LEVEL` (default: `WARNING`): Level for Python standard logging.
*   `HEAVY_TASK_LIMIT` (default: `1`): Semaphore limit for concurrent strategist command execution (FastF1 calculations are CPU/memory heavy).

