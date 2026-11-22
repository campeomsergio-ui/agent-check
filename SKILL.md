---
name: agent-check
description: Audits a Claude Code project setup and writes a one-page report of what to fix. Checks permissions (bypass mode, unlimited tool allows, risky pre-approved commands, missing deny rules), hooks (missing scripts, uninstalled commands, swallowed errors), MCP servers in .mcp.json (plain http, servers that cannot start, inline keys), secrets in project files, and basics (CLAUDE.md/AGENTS.md, .gitignore for .env). Use when the user asks to check, audit or harden their Claude Code, agent or MCP setup, or before sharing a repo.
license: MIT
---

# agent-check

Run the bundled script on the project the user wants checked. It needs Python 3 only, reads files, and never runs hooks, MCP servers or project code.

```bash
python3 <this-skill-dir>/audit.py <project-dir>
```

Add `--no-user` to skip the user's `~/.claude/settings.json`, or `--out report.md` to write a file. Exit code 1 means something is in "Fix first".

## Then

1. Show the report as it is. Recognised keys are masked, but commands, rules and URLs are quoted, so don't paste it anywhere public for the user.
2. For each "Fix first" item, offer the concrete change (the exact settings.json edit, .gitignore line or hook path) and apply it only when the user agrees.
3. Rerun the script to confirm the item is gone.

## Limits

It only reads files. It can't see how the agent behaves in a session, whether MCP servers connect, or which tasks fail. Say so if the user asks whether their setup is "safe" overall. For a human review of real sessions: https://guraforge.com/agent-check/
