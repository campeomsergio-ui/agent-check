"""Regression cases from the review of agent-check v1 (1826669).

Run from the repository root: python3 tests/v1_regressions.py .
"""
from pathlib import Path
import tempfile
import unittest

from v1_pairs import AUDIT, LOCAL, MCP, SETTINGS, USER, hook, write_project


class V1Regressions(unittest.TestCase):
    def findings(self, files):
        with tempfile.TemporaryDirectory() as scratch:
            root, home = write_project(Path(scratch), files)
            return {item["title"]: item for item in AUDIT.audit(root, home)}

    def test_explicit_boolean_precedence_and_exact_title(self):
        title = "configured hooks are disabled"
        settings_with_hook = hook("echo")
        cases = (
            ("user", {}, {}, True, USER),
            ("project false over user true", {"disableAllHooks": False}, {}, True, None),
            ("project true over user false", {"disableAllHooks": True}, {}, False, SETTINGS),
            ("local false over project true", {"disableAllHooks": True},
             {"disableAllHooks": False}, True, None),
            ("local true over project false", {"disableAllHooks": False},
             {"disableAllHooks": True}, False, LOCAL),
        )
        for name, project, local, user, source in cases:
            with self.subTest(name=name):
                findings = self.findings({
                    SETTINGS: settings_with_hook | project,
                    LOCAL: local,
                    USER: {"disableAllHooks": user},
                })
                if source:
                    source_label = "~/.claude/settings.json" if source == USER else source
                    self.assertIn(f"true in {source_label}", findings[title]["detail"])
                else:
                    self.assertNotIn(title, findings)

    def test_disabling_empty_hook_groups_is_quiet(self):
        settings = {"disableAllHooks": True, "hooks": {"PreToolUse": [{"hooks": []}]}}
        self.assertNotIn("configured hooks are disabled", self.findings({SETTINGS: settings}))

    def test_only_string_approval_entries_match_declared_names(self):
        files = {MCP: {"mcpServers": {"7": {"type": "http", "url": "https://example.invalid/mcp"}}}}
        title = "conflicting project MCP approvals for '7'"
        denied = {LOCAL: {"disabledMcpjsonServers": ["7"]}}
        self.assertIn(title, self.findings(files | denied | {SETTINGS: {"enabledMcpjsonServers": ["7"]}}))
        self.assertNotIn(title, self.findings(files | denied | {SETTINGS: {"enabledMcpjsonServers": [7]}}))

    def test_empty_settings_array_is_reported(self):
        title = ".claude/settings.json is not a settings object"
        self.assertNotIn(title, self.findings({SETTINGS: {}}))
        self.assertEqual("high", self.findings({SETTINGS: []}).get(title, {}).get("severity"))

    def test_empty_mcp_server_array_is_reported(self):
        title = "mcpServers must be an object"
        self.assertNotIn(title, self.findings({MCP: {"mcpServers": {}}}))
        self.assertEqual("high", self.findings({MCP: {"mcpServers": []}}).get(title, {}).get("severity"))


if __name__ == "__main__":
    unittest.main()
