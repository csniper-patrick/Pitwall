# Task: Mock API Replay Verification

Run and verify the offline simulated replay of live timing data to validate publisher and consumer services.

---

## 1. Objective

Simulate a full race session locally using archived data to test publisher ingestion, RedisJSON delta updates, and Discord bot command handling without needing a live Grand Prix.

---

## 2. Steps

1. **Spin up mock environment:**
   ```bash
   docker compose -f compose.dev.yaml up -d
   ```
2. **Verify SignalR & proxy replay:**
   ```bash
   docker compose -f compose.dev.yaml logs --tail 50 -f proxy signalr
   ```
   * Ensure `signalr` broadcasts message frames.
   * Ensure `proxy` responds with HTTP 200 to negotiation endpoints.
3. **Check Publisher Processing:**
   ```bash
   docker compose -f compose.dev.yaml logs --tail 50 -f publisher-timing publisher-race-control
   ```
4. **Inspect Redis State:**
   Verify keys in Redis (`localhost:8001` or via `redis-cli`):
   ```bash
   docker exec -it pitwall-redis-1 redis-cli KEYS "*"
   ```
5. **Teardown:**
   ```bash
   docker compose -f compose.dev.yaml down
   ```

