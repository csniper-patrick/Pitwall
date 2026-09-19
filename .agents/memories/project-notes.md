# Memory: Project Architectural Notes & Timing Quirks

Persistent notes on Formula 1 Live Timing SignalR protocols and Redis state management patterns.

---

## 1. SignalR Live Timing Protocol Quirks

*   **Negotiation Handshake:** The F1 live timing service uses Microsoft SignalR protocol. Clients must perform an initial HTTP GET to `/signalr/negotiate` with client protocol `1.5` before upgrading to WebSocket.
*   **Heartbeats & Reconnects:** Connection drops are frequent during session transitions. Publishers must implement backoff reconnection (`RETRY=True`).
*   **Compression & Encoding:** Data frames may be Base64-encoded or raw JSON strings; `publisher/utils.py` handles parsing.

---

## 2. RedisJSON State Patterns

*   **Delta Payloads:** Live timing sends incremental dictionaries (e.g., only updating a sector time or speed trap).
*   **`updateDictDelta`:** Recursive dictionary patching is required so that existing lap/sector times are not erased when a single field updates.
*   **Pub/Sub Channels:** Updates published to Redis channels trigger push notifications in Discord services (`discord/*.py`).

