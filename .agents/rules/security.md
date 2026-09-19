# Security & Credential Management

This document defines the security rules and secrets handling for the Pitwall project.

---

## 1. Secrets & Sensitive Data

*   **Never Hardcode Secrets:** Never commit bot tokens, webhook URLs, or API credentials into tracked files.
*   **Environment Files:**
    *   Store local credentials in `discord.env` and `publish.env`.
    *   Ensure all `*.env` files containing real secrets remain in `.gitignore`.
    *   Only `*.env.example` templates should be committed to version control.
*   **Discord Tokens & Webhooks:**
    *   `DISCORD_BOT_TOKEN`: Grant only required bot intents (slash commands, message handling).
    *   `DISCORD_WEBHOOK`: Treat push notification webhook URLs as confidential; leaking them allows unauthorized messages in Discord channels.

---

## 2. Network & Transport Security

*   **SSL Configuration:**
    *   In production (`compose.yaml`), ensure `USE_SSL=True` for connecting to Formula 1 Live Timing (`livetiming.formula1.com`).
    *   In local development with mock API (`compose.dev.yaml`), `USE_SSL=False` is routed to the local proxy. Never disable SSL in production configurations.
*   **Redis Broker Exposure:**
    *   Redis Stack runs internally within the Docker bridge network (`redis:6379`).
    *   RedisInsight web UI (`8001`) is intended for local inspection and must not be exposed to the public internet without authentication.

---

## 3. Operational Safety & Sandboxing

*   **Non-destructive Execution:** Do not run arbitrary shell scripts or elevate permissions unless explicitly required for container administration.
*   **Command Isolation:** Always run commands with explicit working directories (`Cwd`) and within container or virtual environments (`.venv`).

