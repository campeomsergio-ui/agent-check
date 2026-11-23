"""Compatibility and report-output pairs for the agent-check v1.3 review."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import HIGH, check_hooks, check_skills, finding, render


class ReviewFixtures(unittest.TestCase):
    def test_claude_code_description_fallback(self):
        for frontmatter in ("name: lint\n", "name: lint\ndescription: Lint this project.\n"):
            with self.subTest(frontmatter=frontmatter), TemporaryDirectory() as temp:
                root = Path(temp)
                skill = root / ".claude/skills/lint/SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text(f"---\n{frontmatter}---\nLint this project.\n")
                self.assertFalse(any(item["severity"] == HIGH for item in check_skills(root)))

    def test_valid_yaml_name_with_inline_comment(self):
        for name in ("lint # Local command", "lint"):
            with self.subTest(name=name), TemporaryDirectory() as temp:
                root = Path(temp)
                skill = root / ".claude/skills/lint/SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text(f"---\nname: {name}\ndescription: Lint this project.\n---\n")
                self.assertEqual(check_skills(root), [])

    def test_github_annotations_preserve_text(self):
        for detail, expected in (("line 1\r\nline 2 %", "line 1%0D%0Aline 2 %25"),
                                 ("input 100%", "input 100%25")):
            with self.subTest(detail=detail):
                item = finding(HIGH, "Fixture", "Example", detail, "Fix it.")
                output = render("github", Path("."), [item], False)
                self.assertEqual(output.splitlines(), [
                    f"::error title=agent-check Fixture::Example: {expected} Fix: Fix it."
                ])

    def test_hook_details_omit_recognized_key(self):
        synthetic_key = "sk_live_" + "Z" * 24
        for value in (synthetic_key, "placeholder"):
            with self.subTest(contains_key=value == synthetic_key), TemporaryDirectory() as temp:
                root = Path(temp)
                hooks = {"PostToolUse": [{"hooks": [
                    {"type": "command", "command": f"echo {value} || true"}
                ]}]}
                settings = ".claude/settings.json"
                items = check_hooks(root, settings, hooks)
                self.assertTrue(any("hides its own failures" in item["title"] for item in items))
                self.assertTrue(all(synthetic_key not in render(fmt, root, items, False)
                                    for fmt in ("md", "json", "github", "sarif")))


if __name__ == "__main__":
    unittest.main()
