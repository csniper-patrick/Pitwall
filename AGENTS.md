# Pitwall - Agent Directives & Context Router

You are operating inside the Pitwall repository. Follow the core system architecture and reference specific operational files below depending on your task.

> **Rule:** Only read the specific workflow or rule file relevant to the current task to conserve context window.

---

## 1. Architecture & Conventions

*   **System Overview & Architecture:** [.agents/overview.md](.agents/overview.md)
    *   *Trigger:* Consult when understanding service topology, Redis pub/sub flows, directory structure, or environment variable configuration.
*   **Coding Style & Technical Standards:** [.agents/rules/coding-style.md](.agents/rules/coding-style.md)
    *   *Trigger:* Consult whenever writing or modifying Python code, imports, async routines, or state delta logic.
*   **Dependencies & Ecosystem:** [.agents/rules/dependencies.md](.agents/rules/dependencies.md)
    *   *Trigger:* Consult when adding, updating, or reviewing external packages, third-party libraries, or runtime requirements.
*   **Agent Behavioral Rules & Guardrails:** [.agents/rules/agent-rules.md](.agents/rules/agent-rules.md)
    *   *Trigger:* Consult for fundamental agent operating principles, non-destructive guidelines, and core coding rules (Rules 1–13).
*   **Security & Secrets Management:** [.agents/rules/security.md](.agents/rules/security.md)
    *   *Trigger:* Consult when handling tokens (`DISCORD_BOT_TOKEN`), webhooks, SSL configurations, or credentials.

---

## 2. Workflows & SOPs

*   **Deployment & Operational Commands:** [.agents/workflows/deployment.md](.agents/workflows/deployment.md)
    *   *Trigger:* Consult when starting, stopping, or managing docker/podman compose environments (dev mock vs. prod).
*   **Testing & Debugging Runbook:** [.agents/workflows/testing.md](.agents/workflows/testing.md)
    *   *Trigger:* Consult when running mock API replay tests, inspecting Redis state/channels, or capturing telemetry logs.
*   **Git Standards & Staging Rules:** [.agents/workflows/git-standards.md](.agents/workflows/git-standards.md)
    *   *Trigger:* Consult before staging, diffing, or committing changes (Strict rule: do not commit unless explicitly instructed).

---

## 3. Skills, Tasks & Knowledge

*   **Reusable Skills:** [.agents/skills/](.agents/skills/)
    *   *Live Data Logger:* [.agents/skills/live-data-logger/skill.md](.agents/skills/live-data-logger/skill.md) — Stream and archive live race sessions.
*   **Standard Tasks:** [.agents/tasks/](.agents/tasks/)
    *   *Mock Replay Verification:* [.agents/tasks/mock-replay/task.md](.agents/tasks/mock-replay/task.md) — Offline validation task using simulated replays.
*   **Persistent Memories & Notes:** [.agents/memories/](.agents/memories/)
    *   *Project Notes:* [.agents/memories/project-notes.md](.agents/memories/project-notes.md) — F1 SignalR quirks and RedisJSON state conventions.
*   **Tool Protocols:** [.agents/mcp.json](.agents/mcp.json) — Model Context Protocol configuration.

---

## 4. Specialized Personas

*   **Code Reviewer:** [.agents/personas/reviewer.md](.agents/personas/reviewer.md)
    *   *Trigger:* Adopt when reviewing code changes, checking async integrity, or verifying non-breaking edits.
*   **Test Engineer:** [.agents/personas/test-engineer.md](.agents/personas/test-engineer.md)
    *   *Trigger:* Adopt when simulating live sessions, verifying SignalR/proxy behavior, or debugging Redis pub/sub streams.
