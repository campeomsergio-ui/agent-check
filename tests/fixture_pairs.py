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
    ("settings JSON", "not valid JSON", {SETTINGS: "{"}, {SETTINGS: {}}),
    ("bypass mode", "skips all permission prompts",
     {SETTINGS: {"permissions": {"defaultMode": "bypassPermissions"}}},
     {SETTINGS: {"permissions": {"defaultMode": "default"}}}),
    ("broad allow", "allows whole tools",
     {SETTINGS: allow("Bash")}, {SETTINGS: allow("Bash(npm test)")}),
    ("sensitive command allow", "pre-approves risky commands",
     {SETTINGS: allow("Bash(git push *)")}, {SETTINGS: allow("Bash(git status)")}),
    ("missing deny", "has no deny rules",
     {SETTINGS: {"permissions": {"allow": ["Bash"]}}}, {SETTINGS: allow("Bash")}),
    ("narrow allow needs no generic deny", "has no deny rules",
     {SETTINGS: {"permissions": {"allow": ["Bash"]}}},
     {SETTINGS: {"permissions": {"allow": ["Bash(npm test)"]}}}),
    ("user settings", "skips all permission prompts",
     {USER: {"permissions": {"defaultMode": "bypassPermissions"}}},
     {USER: {"permissions": {"defaultMode": "default"}}}),
    ("local settings", "allows whole tools", {LOCAL: allow("Edit")}, {LOCAL: allow("Bash(npm test)")}),
    ("hook file", "hook points at a missing file",
     {SETTINGS: hook("$CLAUDE_PROJECT_DIR/absent.sh")},
     {SETTINGS: hook("$CLAUDE_PROJECT_DIR/check.sh"), "check.sh": "#!/bin/sh\nexit 0\n"}),
    ("relative hook file", "hook points at a missing file",
     {SETTINGS: hook("./absent.sh")}, {SETTINGS: hook("./check.sh"), "check.sh": "#!/bin/sh\nexit 0\n"}),
    ("interpreted hook file", "hook points at a missing file",
     {SETTINGS: hook("python3 absent.py")}, {SETTINGS: hook("python3 check.py"), "check.py": "pass\n"}),
    ("hook executable", "not installed here",
     {SETTINGS: hook("fixture-command-that-does-not-exist")}, {SETTINGS: hook(sys.executable)}),
    ("hook masking", "hook hides its own failures",
     {SETTINGS: hook(f"{sys.executable} check.py || true"), "check.py": "pass\n"},
     {SETTINGS: hook(f"{sys.executable} check.py"), "check.py": "pass\n"}),
    ("MCP JSON", "not valid JSON", {MCP: "{"}, {MCP: server(type="http", url="https://example.test/mcp")}),
    ("MCP HTTP", "uses plain http",
     {MCP: server(type="http", url="http://example.test/mcp")},
     {MCP: server(type="http", url="http://127.0.0.1:8080/mcp")}),
    ("IPv6 MCP loopback", "uses plain http",
     {MCP: server(type="http", url="http://example.test/mcp")},
     {MCP: server(type="http", url="http://[::1]:8080/mcp")}),
    ("MCP executable", "can't start here",
     {MCP: server(type="stdio", command="fixture-mcp-not-on-path")},
     {MCP: server(type="stdio", command=sys.executable)}),
    ("MCP deferred command", "can't start here",
     {MCP: server(type="stdio", command="fixture-mcp-not-on-path")},
     {MCP: server(type="stdio", command="${FIXTURE_MCP_COMMAND}")}),
    ("MCP literal credential", "has a secret written",
     {MCP: server(type="stdio", command=sys.executable, env={"API_TOKEN": "fictional-fixture-value"})},
     {MCP: server(type="stdio", command=sys.executable, env={"API_TOKEN": "${FIXTURE_TOKEN}"})}),
    ("environment filename", "is in the repo",
     {".env.local": "NAME=fictional\n"}, {".env.example": "NAME=\n"}),
    ("key marker", "AWS access key found",
     {"fixture.txt": "AKIA" + "Z" * 16}, {"fixture.txt": "AWS_ACCESS_KEY_ID=\n"}),
    ("project instructions", "No CLAUDE.md or AGENTS.md",
     {MEMORY: None}, {MEMORY: None, "AGENTS.md": "# Instructions\n"}),
    ("local instructions", "No CLAUDE.md or AGENTS.md",
     {MEMORY: None}, {MEMORY: None, "CLAUDE.local.md": "# Instructions\n"}),
    ("long instructions", "is very long",
     {MEMORY: "Project instructions.\n" * 2100}, {MEMORY: "Run tests first.\n"}),
    ("environment ignore", ".env is not in .gitignore",
     {IGNORE: "node_modules/\n"}, {IGNORE: ENV_IGNORE}),
    ("anchored ignore", ".env is not in .gitignore",
     {IGNORE: "node_modules/\n"}, {IGNORE: "/.env*\n!/.env.example\n"}),
    ("local settings ignore", "settings.local.json is not ignored",
     {IGNORE: ".env*\n", SETTINGS: {}}, {SETTINGS: {}}),
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
