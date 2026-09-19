# Pitwall - Agent Directives & Context Router

You are operating inside the Pitwall repository. Follow the core system architecture and reference specific operational files below depending on your task.

> **Rule:** Only read the specific workflow or rule file relevant to the current task to conserve context window.

---

## 1. Architecture & Conventions

*   **System Overview & Architecture:** [.agents/overview.md](.agents/overview.md)
    *   *Trigger:* Consult when understanding service topology, Redis pub/sub flows, directory structure, or environment variable configuration.
*   **Coding Style & Technical Standards:** [.agents/rules/coding-style.md](.agents/rules/coding-style.md)
    *   *Trigger:* Consult whenever writing or modifying Python code, imports, async routines, or state delta logic.
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

## 3. Specialized Personas

*   **Code Reviewer:** [.agents/personas/reviewer.md](.agents/personas/reviewer.md)
    *   *Trigger:* Adopt when reviewing code changes, checking async integrity, or verifying non-breaking edits.
*   **Test Engineer:** [.agents/personas/test-engineer.md](.agents/personas/test-engineer.md)
    *   *Trigger:* Adopt when simulating live sessions, verifying SignalR/proxy behavior, or debugging Redis pub/sub streams.
