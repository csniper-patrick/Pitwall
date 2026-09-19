# Deployment & Environment Operations

This runbook describes how to manage and run Pitwall services across development and production environments using `docker compose` or `podman compose`.

---

## 1. Prerequisites & Environment Setup

Before starting services, ensure required environment configuration files are prepared:
```bash
# Publisher configuration
cp publish.env.example publish.env

# Discord bot configuration
cp discord.env.example discord.env
```

---

## 2. Development Environment (Mock API Enabled)

The mock API environment redirects SignalR and static HTTP requests to a local proxy, simulating live sessions using stored archives in `mock-api/`.

### Start Services
```bash
# Run all development containers in background
docker compose -f compose.dev.yaml up -d
```
*(Or use `podman compose -f compose.dev.yaml up -d`)*

### Inspect Logs
```bash
# View all service logs
docker compose -f compose.dev.yaml logs -f

# View specific service logs (e.g., proxy, signalr, or discord-bot)
docker compose -f compose.dev.yaml logs -f proxy signalr
docker compose -f compose.dev.yaml logs -f discord-bot
```

### Stop Development Environment
```bash
docker compose -f compose.dev.yaml down
```

---

## 3. Production Environment (Live F1 Timing Feed)

The production environment connects directly to the Formula 1 live timing SignalR stream and pushes live updates to Discord.

### Start Production Services
```bash
docker compose -f compose.yaml up -d
```

### Inspect Logs
```bash
docker compose -f compose.yaml logs -f [service-name]
```

### Stop Production Environment
```bash
docker compose -f compose.yaml down
```

---

## 4. Operational Troubleshooting

*   **Redis Connectivity Issues:** Check if Redis Stack is healthy via `docker compose ps` and verify port `6379` is accessible to internal containers.
*   **Discord Slash Command Sync:** Ensure `DISCORD_BOT_TOKEN` has appropriate application command permissions in the Discord Developer Portal.

