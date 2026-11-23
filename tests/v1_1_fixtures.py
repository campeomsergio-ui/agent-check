from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys

KIT = Path(sys.argv[1]).resolve()
AUDIT = KIT / "audit.py"
CASES = [
    ("permissions collections", {".claude/settings.json": {"permissions": {"allow": 7}}}, "permissions.allow must be a list of strings",
     {".claude/settings.json": {"permissions": {"allow": ["Bash(npm test:*)"]}}}),
    ("MCP transport fields", {".mcp.json": {"mcpServers": {"fixture": {"url": 7}}}}, "MCP server 'fixture' url must be a string",
     {".mcp.json": {"mcpServers": {"fixture": {"type": "http", "url": "https://example.invalid/mcp"}}}}),
    ("hook entry shapes", {".claude/settings.json": {"hooks": {"PreToolUse": [{"hooks": [7]}]}}},
     "PreToolUse hook entry must be an object",
     {".claude/settings.json": {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "echo"}]}]}}}),
]

def invoke(root, *options):
    return subprocess.run([sys.executable, str(AUDIT), str(root), "--no-user", *options],
                          capture_output=True, text=True, timeout=8)

def put(root, path, obj):
    f = root / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(obj), encoding="utf-8")

def seed(root):
    root.mkdir()
    (root / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    (root / ".gitignore").write_text(".env*\n.claude/settings.local.json\n", encoding="utf-8")

def run_cases():
    failed = 0
    for name, trigger, expected, control in CASES:
        for is_trigger, files in ((True, trigger), (False, control)):
            with TemporaryDirectory() as raw:
                root = Path(raw) / "project"
                seed(root)
                for path, obj in files.items():
                    put(root, path, obj)
                if is_trigger:
                    put(root, ".claude/settings.local.json", {"permissions": {"defaultMode": "bypassPermissions"}})
                observed = invoke(root)
                matched = (observed.returncode == 1 and expected in observed.stdout
                           and "skips all permission prompts" in observed.stdout and not observed.stderr
                           if is_trigger else observed.returncode == 0 and expected not in observed.stdout)
                print(f"{'PASS' if matched else 'RED'} {name} {'trigger' if is_trigger else 'control'}: "
                      f"exit={observed.returncode}, traceback={'Traceback' in observed.stderr}")
                failed += not matched
    return failed

def verify_existing():
    with TemporaryDirectory() as raw:
        root = Path(raw) / "project"
        seed(root)
        unset = invoke(root, "--out")
        print(f"missing --out operand: exit={unset.returncode}, IndexError={'IndexError' in unset.stderr}")
        put(root, ".mcp.json", {"mcpServers": {"fixture": {"url": "http://example.invalid/mcp?token=fixture-marker"}}})
        print(f"synthetic URL value in report: {'fixture-marker' in invoke(root).stdout}")
        put(root, ".mcp.json", {"mcpServers": []})
        print(f"empty list for mcpServers: exit={invoke(root).returncode}")
        put(root, ".mcp.json", {"mcpServers": {"123": {"type": "http", "url": "https://example.invalid/mcp"}}})
        put(root, ".claude/settings.json", {"enabledMcpjsonServers": [123], "disabledMcpjsonServers": ["123"]})
        print(f"number coerced into named approval: {'conflicting project MCP approvals' in invoke(root).stdout}")
        put(root, ".mcp.json", {"mcpServers": {}})
        put(root, ".claude/settings.json", {"disableAllHooks": True, "hooks": {"PreToolUse": []}})
        print(f"empty hook group flagged configured: {'configured hooks are disabled' in invoke(root).stdout}")
    generated = invoke(KIT / "examples" / "messy-project")
    expected = (KIT / "examples" / "sample-report.md").read_text(encoding="utf-8")
    print(f"sample: exit={generated.returncode}, exact={generated.stdout == expected}")

if __name__ == "__main__":
    verify_existing()
    sys.exit(bool(run_cases()))
