import json, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit

FAKE_KEY = "sk-ant-" + "a1" * 20


def project(files):
    d = Path(tempfile.mkdtemp())
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content if isinstance(content, str) else json.dumps(content))
    return d


def titles(root):
    return [f["title"] for f in audit.audit(root)]


class Clean(unittest.TestCase):
    def test_clean_project_has_no_findings(self):
        root = project({"CLAUDE.md": "Run npm test.", ".gitignore": ".env*\n.claude/settings.local.json\n",
                        ".claude/settings.json": {"permissions": {"allow": ["Bash(npm test:*)"], "deny": ["Read(./.env*)"]}}})
        self.assertEqual(audit.audit(root), [])
        self.assertIn("No blocking problems", audit.report(root, []))


class Problems(unittest.TestCase):
    def test_broad_and_bypass_permissions(self):
        root = project({".claude/settings.json": {"permissions": {"defaultMode": "bypassPermissions", "allow": ["Bash", "Bash(rm -rf:*)"]}}})
        t = " ".join(titles(root))
        for part in ["skips all permission prompts", "allows whole tools", "risky commands", "no deny rules"]:
            self.assertIn(part, t)

    def test_invalid_settings_json(self):
        root = project({".claude/settings.json": "{not json"})
        self.assertTrue(any("not valid JSON" in t for t in titles(root)))

    def test_hook_missing_file_and_swallowed_errors(self):
        hooks = {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "/nope/fmt.sh || true"}]}]}
        t = " ".join(titles(project({".claude/settings.json": {"hooks": hooks}})))
        self.assertIn("missing file", t)
        self.assertIn("hides its own failures", t)

    def test_mcp_http_missing_command_and_literal_secret(self):
        mcp = {"mcpServers": {"a": {"type": "http", "url": "http://api.example.com/mcp"},
                              "b": {"command": "definitely-not-installed-xyz", "env": {"API_TOKEN": "abc123"}}}}
        t = " ".join(titles(project({".mcp.json": mcp})))
        for part in ["plain http", "can't start here", "secret written into .mcp.json"]:
            self.assertIn(part, t)

    def test_env_reference_is_not_a_literal_secret(self):
        mcp = {"mcpServers": {"b": {"command": "python3", "env": {"API_TOKEN": "${API_TOKEN}"}}}}
        self.assertFalse(any("secret written" in t for t in titles(project({".mcp.json": mcp}))))

    def test_secret_in_file_is_found_but_never_printed(self):
        root = project({"src/config.py": f'KEY = "{FAKE_KEY}"', ".env": "X=1", ".env.example": "X="})
        findings = audit.audit(root)
        t = " ".join(f["title"] for f in findings)
        self.assertIn("Anthropic API key found in src/config.py", t)
        self.assertIn(".env is in the repo", t)
        self.assertNotIn(".env.example is in the repo", t)
        self.assertNotIn(FAKE_KEY, audit.report(root, findings))

    def test_missing_instructions_and_gitignore(self):
        t = " ".join(titles(project({"a.txt": "x"})))
        self.assertIn("No CLAUDE.md", t)
        self.assertIn(".env is not in .gitignore", t)


class Cli(unittest.TestCase):
    def test_exit_code_and_report_file(self):
        root = project({"k.txt": FAKE_KEY})
        out = root / "report.md"
        r = subprocess.run([sys.executable, str(Path(audit.__file__)), str(root), "--out", str(out)], capture_output=True)
        self.assertEqual(r.returncode, 1)
        text = out.read_text()
        self.assertIn("Fix before relying on this setup", text)
        self.assertLess(len(text.splitlines()), 60)


if __name__ == "__main__":
    unittest.main()
