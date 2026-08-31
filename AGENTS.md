# Pitwall - Agent Guidelines

This file provides system context, architectural guidelines, development workflows, and coding conventions for autonomous AI agents working in the Pitwall codebase.

---

## 1. Project Overview & Architecture

**Pitwall** is a Python-based Discord bot for Formula 1 fans. It connects to the live F1 timing data feeds, publishes structured data to a Redis broker, and consumes this data to push real-time updates and handle interactive on-demand slash commands.

The project is structured as a decoupled microservice architecture:
1. **Publisher Services (`publisher/`)**: Connect to the live timing WebSocket endpoints (SignalR), retrieve JSON payloads, apply deltas to the master Redis JSON store, and publish updates to dedicated Redis channels.
2. **Redis Broker (`redis-stack`)**: Serves as a low-latency data store (using RedisJSON) and pub/sub message broker.
3. **Discord Services (`discord/`)**: Listen to Redis pub/sub channels, format data into Discord embeds using webhooks/web-requests, and run a Discord bot client to handle slash commands.
4. **Mock API (`mock-api/`)**: Simulates the F1 live timing SignalR and HTTP endpoints by replay-ing historical event streams (from static archives). It is used for local development and testing.

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

---

## 4. Operational Commands

Use `docker compose` (or `podman compose` as needed) in the project root:

### Development Environment (Mock API Enabled)
The mock API environment redirects SignalR and static HTTP requests to a local proxy, simulating live sessions using stored archives.
```bash
# Start in background
docker compose -f compose.dev.yaml up -d

# View service logs
docker compose -f compose.dev.yaml logs -f [service-name]

# Stop environment
docker compose -f compose.dev.yaml down
```

### Production Environment (Real F1 Live Timing Feed)
```bash
# Start in background
docker compose -f compose.yaml up -d

# Stop environment
docker compose -f compose.yaml down
```

---

## 5. Development Conventions & Code Style

*   **Language & Runtime:** Python 3.13.
*   **Asynchronous I/O:** Services are built around `asyncio`. Use `redis.asyncio` for interacting with Redis, and `websockets` for SignalR live-timing websocket connections.
*   **Naming Conventions:**
    *   Python filenames: `snake_case.py`
    *   Functions & variables: `snake_case` or `mixedCase` (keep local style consistency. E.g., `publisher/utils.py` uses `timeStr2msec` and `updateDictDelta`).
*   **Imports Order:**
    1. Standard libraries (`asyncio`, `json`, `os`, `urllib.parse`, etc.).
    2. Third-party packages (`redis.asyncio`, `discord`, `fastf1`, `requests`, `websockets`, etc.).
    3. Project local modules (e.g., `from utils import *`).
*   **State Synchronization:** Live timing updates arrive as JSON deltas. Use the `updateDictDelta` helper function in `utils.py` to recursively apply updates to Python dictionaries and RedisJSON.
*   **Docstrings:** Maintain Google-style or standard Python docstrings for classes, functions, and files.

---

## 6. Testing & Debugging

1. Run the development environment with `docker compose -f compose.dev.yaml up -d`.
2. Inspect the mock-api logs using `docker compose -f compose.dev.yaml logs -f proxy signalr` to verify mock replay traffic.
3. Test bot commands inside Discord or review RedisJSON keys (accessible through RedisInsight port `8001`).
4. To capture raw telemetry or timing JSON streams from a live race weekend, use the `mock-api/live-data-log-json.py` script.

---

## 7. Crucial Rules for AI Agents

*   **Preserve Existing Context:** Do not delete existing comments, helper utilities, or docstrings unless explicitly asked.
*   **No cd commands:** Always propose `run_command` with correct `Cwd` fields. Never use `cd` in shell commands.
*   **Async Integrity:** Keep the publishers and listeners async. Never block the event loop with synchronous network/disk calls; use executor blocks or async libraries where needed.
*   **Respect Heavy Tasks:** FastF1 commands (`/strategist`) can consume significant CPU/memory. Respect the `task_semaphore` / `HEAVY_TASK_LIMIT` limits inside slash commands to prevent overloading containers.
*   **Do Not Commit Unless Explicitly Told:** Do not create git commits or run `git commit` unless explicitly instructed to do so by the user. Leave all modified files uncommitted/unstaged for user review and approval.

---

## 8. Agent Coding Rules

These rules apply to every task in this project unless explicitly overridden.
Bias: caution over speed on non-trivial work. Use judgment on trivial tasks.

*   **Rule 1 — Think Before Coding:**
    *   State assumptions explicitly. If uncertain, ask rather than guess.
    *   Present multiple interpretations when ambiguity exists.
    *   Push back when a simpler approach exists.
    *   Stop when confused. Name what's unclear.
*   **Rule 2 — Simplicity First:**
    *   Minimum code that solves the problem. Nothing speculative.
    *   No features beyond what was asked. No abstractions for single-use code, scripts, or configurations.
    *   Test: would a senior engineer say this is overcomplicated? If yes, simplify.
*   **Rule 3 — Surgical Changes:**
    *   Touch only what you must. Clean up only your own mess.
    *   Don't "improve" adjacent code, playbooks, comments, or formatting.
    *   Don't refactor what isn't broken. Match existing style.
*   **Rule 4 — Goal-Driven Execution:**
    *   Define success criteria. Loop until verified.
    *   Don't follow steps blindly. Define success and iterate.
    *   Strong success criteria let you loop independently.
*   **Rule 5 — Leverage the model's strengths:**
    *   Use LLM for: large-scale context analysis, multi-modal data extraction, architectural drafting, and cross-file summarization.
    *   Do NOT use LLM for: deterministic transforms, executing pipelines, or tasks where simple scripts suffice.
    *   If a native tool or code can answer, let it.
*   **Rule 6 — Context is vast, but focus is critical:**
    *   While context windows are large, do not unnecessarily bloat context with irrelevant logs or unrelated data dumps.
    *   If the project shifts to a completely new domain, summarize the current state and start fresh to maintain absolute precision.
    *   Surface any context drift. Do not silently lose track of the core objective.
*   **Rule 7 — Surface conflicts, don't average them:**
    *   If two patterns or configurations contradict, pick one (more recent / more tested).
    *   Explain why. Flag the other for cleanup.
    *   Don't blend conflicting architectures or patterns.
*   **Rule 8 — Read before you write:**
    *   Before adding code, read exports, immediate callers, shared utilities, and relevant deployment pipelines.
    *   "Looks orthogonal" is dangerous. If unsure why code or infrastructure is structured a certain way, ask.
*   **Rule 9 — Tests verify intent, not just behavior:**
    *   Tests (and CI checks) must encode WHY behavior matters, not just WHAT it does.
    *   A test that can't fail when business logic or system state changes is wrong.
*   **Rule 10 — Checkpoint after every significant step:**
    *   Summarize what was done, what's verified, what's left.
    *   Don't continue from a state you can't describe back.
    *   If you lose track of the state, stop and restate.
*   **Rule 11 — Match the project's conventions, even if you disagree:**
    *   Conformance > taste inside the repository.
    *   If you genuinely think a convention is harmful, surface it. Don't fork silently or introduce divergent setups.
*   **Rule 12 — Fail loud:**
    *   "Completed" is wrong if anything was skipped silently.
    *   "Pipelines pass" is wrong if any checks were bypassed.
    *   Default to surfacing system errors and uncertainty, not hiding them.
*   **Rule 13 — Do Not Commit Unless Explicitly Told:**
    *   Do not create git commits or run `git commit` unless explicitly instructed to do so by the user.
    *   Leave all modified files uncommitted/unstaged for user review and approval.

