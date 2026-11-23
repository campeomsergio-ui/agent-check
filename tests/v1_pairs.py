"""Materialize isolated, fictional fixture projects and check audit findings. Stdlib only."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


KIT = Path(sys.argv.pop(1)).resolve()
SPEC = importlib.util.spec_from_file_location("audit", KIT / "audit.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

SETTINGS = ".claude/settings.json"
LOCAL = ".claude/settings.local.json"
USER = "@home/.claude/settings.json"
MCP = ".mcp.json"
IGNORE = ".gitignore"
MEMORY = "CLAUDE.md"
ENV_IGNORE = ".env*\n!.env.example\n.claude/settings.local.json\n"
BASE = {MEMORY: "# Project\nRun the local tests.\n", IGNORE: ENV_IGNORE}


def allow(*rules):
    return {"permissions": {"allow": rules, "deny": ["Read(./.env*)"]}}


def hook(command):
    return {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": command}
    ]}]}}


def server(**data):
    return {"mcpServers": {"fixture": data}}


def write_project(directory, updates):
    root = directory / "project"
    home = directory / "home"
    root.mkdir()
    home.mkdir()
    for name, body in (BASE | updates).items():
        if body is None:
            continue
        path = directory / name[1:] if name.startswith("@home/") else root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
    return root, home


CASES = [
    ("invalid permissions shape", "permissions must be an object",
     {".claude/settings.json":{"permissions":["invalid"]}},
     {".claude/settings.json":{"permissions":{}}}),
    ("invalid server shape", "MCP server configuration must be an object",
     {".mcp.json":{"mcpServers":{"fixture":["invalid"]}}},
     {".mcp.json":{"mcpServers":{"fixture":{"type":"http","url":"https://example.invalid/mcp"}}}}),
    ("disabled configured hook", "configured hooks are disabled",
     {".claude/settings.json":{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3"}]}]},"disableAllHooks": True}},
     {".claude/settings.json":{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3"}]}]},"disableAllHooks": False}}),
    ("higher scope overrides hook switch", "configured hooks are disabled",
     {".claude/settings.json":{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3"}]}]},"disableAllHooks": True},".claude/settings.local.json":{"disableAllHooks": True}},
     {".claude/settings.json":{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3"}]}]},"disableAllHooks": True},".claude/settings.local.json":{"disableAllHooks": False}}),
    ("opposing named MCP approvals", "conflicting project MCP approvals",
     {".mcp.json":{"mcpServers":{"fixture":{"type":"http","url":"https://example.invalid/mcp"}}},".claude/settings.json":{"enabledMcpjsonServers":["fixture"]},".claude/settings.local.json":{"disabledMcpjsonServers":["fixture"]}},
     {".mcp.json":{"mcpServers":{"fixture":{"type":"http","url":"https://example.invalid/mcp"}}},".claude/settings.local.json":{"disabledMcpjsonServers":["fixture"]}}),
    ("ignore stale project MCP names", "conflicting project MCP approvals",
     {".mcp.json":{"mcpServers":{"fixture":{"type":"http","url":"https://example.invalid/mcp"}}},".claude/settings.json":{"enabledMcpjsonServers":["fixture"],"disabledMcpjsonServers":["fixture"]}},
     {".mcp.json":{"mcpServers":{"fixture":{"type":"http","url":"https://example.invalid/mcp"}}},".claude/settings.json":{"enabledMcpjsonServers":["old"],"disabledMcpjsonServers":["old"]}}),
]


class FixtureTests(unittest.TestCase):
    def test_each_pair(self):
        for name, title, trigger, control in CASES:
            for expected, files in [(True, trigger), (False, control)]:
                with self.subTest(check=name, trigger=expected), tempfile.TemporaryDirectory() as raw:
                    root, home = write_project(Path(raw), files)
                    # The fixture deliberately runs from outside the project.
                    findings = AUDIT.audit(root, home)
                    self.assertEqual(any(title in item["title"] for item in findings), expected)


if __name__ == "__main__":
    unittest.main()
