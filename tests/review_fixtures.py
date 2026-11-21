"""Read-only local regressions with fictional fixtures for the public audit script."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

source = Path(sys.argv.pop(1)).resolve() / "audit.py"
spec = importlib.util.spec_from_file_location("audit", source)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ReviewFixtures(unittest.TestCase):
    def test_common_project_configurations(self):
        fixtures = {
            "settings shape": (".claude/settings.json", ["fixture"], "Settings", True),
            "MCP shape": (".mcp.json", {"mcpServers": {"fixture": []}}, "MCP", True),
            "quoted command path": (
                ".claude/settings.json",
                {"hooks": {"PreToolUse": [{"hooks": [
                    {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/local checks/check.py"'}
                ]}]}},
                "Hooks",
                False,
            ),
        }
        for name, (config, data, area, expected) in fixtures.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "CLAUDE.md").write_text("Fixture only.\n")
                (root / ".gitignore").write_text(".env*\n.claude/settings.local.json\n")
                script = root / "local checks" / "check.py"
                script.parent.mkdir()
                script.write_text("pass\n")
                file = root / config
                file.parent.mkdir(exist_ok=True)
                file.write_text(json.dumps(data))
                findings = audit.audit(root)
                self.assertEqual(any(f["area"] == area for f in findings), expected)


if __name__ == "__main__":
    unittest.main()
