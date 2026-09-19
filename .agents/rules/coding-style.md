# Coding Style & Technical Guardrails

This document outlines the coding standards, conventions, and technical guardrails for all Python services in Pitwall.

---

## 1. Language & Runtime

*   **Runtime:** Python 3.13.
*   Keep dependencies minimal and declare them in `requirements.txt`.
*   Maintain compatibility with containerized deployment environments.

---

## 2. Asynchronous I/O & Concurrency

*   Services are strictly built around `asyncio`.
*   Use `redis.asyncio` for interacting with Redis.
*   Use `websockets` for SignalR live-timing WebSocket connections.
*   **Async Integrity:** Keep publishers and listeners non-blocking. Never block the event loop with synchronous network/disk calls; offload blocking operations to thread executors (`loop.run_in_executor`) or use async libraries.
*   **Heavy Tasks:** FastF1 operations (`/strategist` commands) consume significant CPU/memory. Respect the `task_semaphore` / `HEAVY_TASK_LIMIT` limits inside slash commands to prevent overloading containers.

---

## 3. Naming Conventions

*   **Filenames:** `snake_case.py`
*   **Functions & Variables:** `snake_case` or `mixedCase` (maintain local consistency within existing files, e.g., `publisher/utils.py` uses `timeStr2msec` and `updateDictDelta`).
*   **Classes:** `PascalCase`
*   **Constants:** `UPPER_SNAKE_CASE`

---

## 4. Imports Ordering

Organize imports into three distinct groups separated by a single blank line:
1. Standard libraries (`asyncio`, `json`, `os`, `urllib.parse`, etc.).
2. Third-party packages (`redis.asyncio`, `discord`, `fastf1`, `requests`, `websockets`, etc.).
3. Project local modules (e.g., `from utils import *`).

---

## 5. State Synchronization

*   Formula 1 Live Timing updates arrive as incremental JSON deltas.
*   Use the `updateDictDelta` helper function in `publisher/utils.py` to recursively apply updates to Python dictionaries and RedisJSON.
*   Ensure atomic or consistent writes to Redis JSON paths to avoid race conditions.

---

## 6. Docstrings & Formatting

*   Maintain Google-style or standard Python docstrings for classes, functions, and modules.
*   Preserve existing comments and docstrings when modifying existing code.

