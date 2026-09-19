# Git Standards & Version Control SOP

This document defines version control policies, branching standards, and commit hygiene for autonomous agents and contributors in the Pitwall repository.

---

## 1. Golden Rule for AI Agents

> [!CAUTION]
> **Do Not Commit Unless Explicitly Told:**
> Do NOT create git commits or run `git commit` unless explicitly instructed to do so by the user. Leave all modified and newly created files uncommitted and unstaged for user review and approval.

---

## 2. Status & Diff Inspection

Before asking for user review or concluding a task:
1. Review modified files and untracked additions:
   ```bash
   git status
   ```
2. Inspect line-by-line diffs to verify minimal surgical changes:
   ```bash
   git diff
   ```
3. Check for any unintentional artifacts, temporary files, or cache files (`__pycache__`, `.pytest_cache`, `.DS_Store`).

---

## 3. Commit Message Standards (When Explicitly Requested)

If and only if the user explicitly instructs you to commit:
*   Use standard Conventional Commits format:
    *   `feat: <description>` for new capabilities (e.g., new live timing endpoints, slash commands)
    *   `fix: <description>` for bug fixes (e.g., reconnect logic, data parsing errors)
    *   `refactor: <description>` for non-functional code reorganization
    *   `docs: <description>` for documentation updates
    *   `chore: <description>` for dependencies or build config changes
*   Keep the first line concise (under 72 characters) and imperative ("Add feature" not "Added feature").

