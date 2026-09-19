# Testing & Debugging Runbook

This runbook covers verifying Pitwall's data ingestion, Redis store updates, and Discord responses using local mock replays and inspection tools.

---

## 1. Local Replay Testing Workflow

Because Formula 1 live timing events only occur during real-world race sessions, development and testing are conducted using simulated replays via the `mock-api/` service.

### Step 1: Start Mock Environment
```bash
docker compose -f compose.dev.yaml up -d
```

### Step 2: Verify Mock API Replay Traffic
Ensure the simulated SignalR and HTTP traffic are streaming properly:
```bash
docker compose -f compose.dev.yaml logs -f proxy signalr
```
*   Verify that `proxy` receives timing requests.
*   Verify that `signalr` broadcasts telemetry and state frames according to the session archive.

---

## 2. Inspecting Redis State

*   **RedisInsight GUI:** Open `http://localhost:8001` in your browser.
*   **Inspecting Keys:** Look for RedisJSON keys under the live timing paths (e.g., timing data, driver statuses, tyre compound tracking).
*   **Pub/Sub Verification:** Inspect active Redis channels to confirm publishers are broadcasting deltas.

---

## 3. Testing Discord Commands

1. In your Discord test server where the bot is invited, test slash commands:
   *   `/race-engineer tyres`: Verify tyre compounds and stints queried from RedisJSON.
   *   `/race-engineer gaps`: Verify live driver intervals and gaps.
   *   `/strategist lap-times`: Verify FastF1 historical session computations.
2. Monitor bot logs for errors or rate limits:
   ```bash
   docker compose -f compose.dev.yaml logs -f discord-bot
   ```

---

## 4. Capturing Live Session Data for New Mocks

To record a live session feed for future testing and mock replays:
1. Run the logging utility during an active F1 session:
   ```bash
   python mock-api/live-data-log-json.py
   ```
2. The output stream files will be written to `data/` or `mock-api/` for replay configuration.

