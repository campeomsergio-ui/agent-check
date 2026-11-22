# agent-check

A one-page check of your Claude Code setup. It reads your config files and tells you what will bite you later.

    curl -fsSLO https://raw.githubusercontent.com/campeomsergio-ui/agent-check/main/audit.py &&
    python3 audit.py /path/to/your/project

Python 3, standard library only. It reads files (git's tracked files when the project is a git repo, otherwise a bounded folder scan) and never runs your hooks, MCP servers or code. Recognised keys are masked, but the report quotes rules, commands and URLs, so read it before you share it.

## Use it as a skill

The repo is also an agent skill (`SKILL.md`). For Claude Code:

    git clone https://github.com/campeomsergio-ui/agent-check ~/.claude/skills/agent-check

Then ask: "check my Claude Code setup".

## What it looks at

- **Permissions** in `.claude/settings.json`, `.claude/settings.local.json` and your own `~/.claude/settings.json`: bypass mode, whole tools allowed with no limits, risky commands pre-approved, no deny rules.
- **Hooks**: scripts that don't exist, commands that aren't installed, hooks that hide their own errors.
- **MCP servers** in `.mcp.json`: plain http, servers that can't start, keys written straight into the file.
- **Secrets** in project files: API keys, tokens, private keys, `.env` files.
- **Basics**: a CLAUDE.md or AGENTS.md, and a `.gitignore` that keeps `.env` and personal settings out of git.

See [a sample report](examples/sample-report.md), made from the deliberately messy project in `examples/messy-project`.

## Options

    python3 audit.py . --out report.md   # write the report to a file
    python3 audit.py . --no-user         # skip ~/.claude/settings.json

It exits with 1 when something in "Fix first" turns up, so you can run it in CI.

## What it can't tell you

It only sees files. It can't see how the agent behaves in a real session, whether MCP servers connect, which tasks fail, or why. If you want a person to look at that, we do it as a fixed-price job: [GuraForge](https://guraforge.com/agent-check/).

## Tests

    python3 -m unittest discover -s tests
    python3 tests/review_fixtures.py .
    python3 tests/fixture_pairs.py .   # 27 pairs: 54 projects that should and shouldn't trigger each check

MIT licence.
