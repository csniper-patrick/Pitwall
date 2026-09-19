# Dependencies & Ecosystem Rules

This document outlines the dependency management policies, third-party library ecosystem, and environment standards for the Pitwall repository.

---

## 1. Core Dependency Principles

*   **No External Dependencies Without Review:** Do not add new external packages or modify `requirements.txt` unless explicitly necessary and reviewed.
*   **Prefer Standard Library:** Whenever possible, use Python's built-in standard library (`asyncio`, `json`, `os`, `urllib.parse`, `math`, `typing`) before adding an external package.
*   **Async Compatibility:** Any proposed library must support or be compatible with non-blocking asynchronous I/O (`asyncio`). Avoid synchronous networking libraries that would block the event loop.
*   **Keep Containers Lean:** Container images build from `requirements.txt`. Adding heavy dependencies directly impacts build times and deployment footprint.

---

## 2. Dependency Inventory & Categorization

The following third-party libraries constitute the current technology stack:

### Core Asynchronous & Network Stack
*   **`redis`:** Asynchronous Redis client (`redis.asyncio`) used for caching, pub/sub communication, and RedisJSON document state storage.
*   **`websockets`:** WebSocket client connecting to the Formula 1 Live Timing SignalR streaming feeds.
*   **`requests`:** Synchronous HTTP library (used in isolated utilities, thread executors, or mock scripts).
*   **`python-dotenv`:** Environment variable loader for local `.env` files.

### Discord Bot & Webhooks
*   **`discord.py`:** Modern asynchronous Discord API wrapper used for slash commands, application commands, and bot client events.
*   **`discordwebhook`:** Lightweight webhook dispatch utility used by publisher push services.

### Formula 1 Telemetry & Historical Data
*   **`fastf1>=3.6.0`:** Formula 1 timing and telemetry data API wrapper.
*   **`pandas` & `numpy`:** Numerical processing and tabular manipulation of lap telemetry.
*   **`matplotlib`, `matplotlib-label-lines`, `seaborn`:** Telemetry visualization and chart generation for `/strategist` slash commands.

### Machine Learning & Audio Processing
*   **`transformers`, `torch`, `accelerate`:** Pre-trained transformer models for team radio speech-to-text transcription.
*   **`wget`:** File retrieval utility for downloading team radio audio snippets.

---

## 3. Environment & Package Management

*   **Runtime Version:** Python 3.13.
*   **Virtual Environment:** Development is conducted within `.venv`. Always execute commands or test scripts using the local virtual environment:
    ```bash
    source .venv/bin/activate
    ```
*   **Updating Requirements:** When dependencies are intentionally updated or added, update `requirements.txt` with appropriate version constraints.

