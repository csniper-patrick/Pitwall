# Skill: Live Data Logger

Capture live Formula 1 timing and telemetry data streams from active race sessions to create local mock archives for testing.

---

## 1. Description

This skill connects to the live Formula 1 timing feed during an active weekend session (FP1, FP2, FP3, Qualifying, Sprint, Race) and streams all incoming SignalR frames into local JSON log archives. These archives can subsequently be mounted into `mock-api/` for replay and integration testing.

---

## 2. Invocation & Procedure

### Prerequisites
* Active Formula 1 session occurring in real-time.
* Network access to `livetiming.formula1.com`.

### Execution Steps
1. Run the recording script:
   ```bash
   python mock-api/live-data-log-json.py
   ```
2. The script negotiates a WebSocket connection and continuously logs frames to `data/` or `mock-api/data/`.
3. Terminate capture with `Ctrl+C` when the session concludes.
4. Verify the output JSON files contain valid timing frames (`TimingData`, `RaceControlMessages`, etc.).

