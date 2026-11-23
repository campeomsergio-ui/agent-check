"""Red/green pairs for project skills and .cursor/mcp.json. Run: python3 tests/skills_cursor_pairs.py"""
from pathlib import Path
import importlib.util, json, tempfile, unittest

spec = importlib.util.spec_from_file_location("audit", Path(__file__).resolve().parents[1] / "audit.py")
AUDIT = importlib.util.module_from_spec(spec); spec.loader.exec_module(AUDIT)


def titles(files):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel, body in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(body if isinstance(body, str) else json.dumps(body))
        return {f["title"] for f in AUDIT.audit(root)}


S = ".claude/skills/deploy/SKILL.md"


class Pairs(unittest.TestCase):
    def test_skill_frontmatter(self):
        good = "---\nname: deploy\ndescription: Deploy the app. Use when asked to ship.\n---\nSteps"
        self.assertFalse({t for t in titles({S: good}) if "Skills" in t or "SKILL" in t})
        self.assertIn(f"{S} has no frontmatter", titles({S: "# Deploy\n"}))
        self.assertIn(f"{S} has no description", titles({S: "---\nname: deploy\n---\n"}))
        self.assertIn(f"{S} name is not lowercase-hyphen", titles({S: "---\nname: Deploy App\ndescription: x\n---\n"}))
        self.assertIn(f"{S} name differs from its folder", titles({S: "---\nname: ship\ndescription: x\n---\n"}))

    def test_cursor_mcp(self):
        bad = {".cursor/mcp.json": {"mcpServers": {"db": {"command": "npx", "env": {"API_TOKEN": "literal"}}}}}
        self.assertIn("MCP server 'db' has a secret written into .cursor/mcp.json", titles(bad))
        ok = {".cursor/mcp.json": {"mcpServers": {"db": {"command": "npx", "env": {"API_TOKEN": "${API_TOKEN}"}}}}}
        self.assertNotIn("MCP server 'db' has a secret written into .cursor/mcp.json", titles(ok))


if __name__ == "__main__":
    unittest.main()
