# Agent reliability audit kit (GuraForge)

One command, one page: checks a Claude Code / agent project setup from files on disk.

    python3 audit.py /path/to/project --out report.md

Checks: permissions (bypass mode, whole-tool allows, risky pre-approvals, no deny rules), hooks (missing scripts, missing binaries, swallowed errors), MCP config (plain http, servers that can't start, literal secrets), secrets in tracked files (values never printed), CLAUDE.md/AGENTS.md, .gitignore for .env and settings.local.json.
Exit code 1 when a high-severity problem is found, so it can run in CI.
Reads only. Never runs hooks, MCP servers or project code. Python 3 standard library only.

Tests: `python3 -m unittest discover -s tests`
