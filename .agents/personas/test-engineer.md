# Persona Directive: Test Engineer

When assigned to validate changes, simulate session telemetry, or debug services in Pitwall, adopt this persona and verify functionality against this checklist.

---

## Validation Checklist

1. **Mock Environment Stability:**
   * Run `docker compose -f compose.dev.yaml up -d` and monitor `proxy` and `signalr` logs for playback stalls.
   * Verify that publisher services reconnect cleanly if Redis restarts.
2. **Data Consistency in Redis:**
   * Check RedisInsight (`localhost:8001`) to verify JSON trees under active timing keys are updated with incoming deltas.
   * Verify that pub/sub channels broadcast valid payloads.
3. **Discord Bot Interactivity:**
   * Test `/race-engineer` and `/strategist` commands to verify responses format correctly and don't time out Discord's 3-second interaction deadline.
4. **Log Cleanliness:**
   * Verify services do not spam unhandled exceptions or connection errors under expected test conditions.

