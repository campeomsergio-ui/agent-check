"""Synthetic source-location, report redaction and skill-name pairs."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import check_hooks, check_secrets, check_skills, render


class ReviewPairs(unittest.TestCase):
    def test_sarif_locations_point_to_source(self):
        for name in ("notes.json", "notes #1.json"):
            with self.subTest(name=name), TemporaryDirectory() as temp:
                root = Path(temp)
                path = root / name
                path.write_text("sk_live_" + "Z" * 24)
                output = json.loads(render("sarif", root, check_secrets(root, [path]), False))
                result, = output["runs"][0]["results"]
                uri = urlsplit(result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"])
                self.assertEqual(unquote(uri.path), name)
                self.assertFalse(uri.fragment)

    def test_redact_before_shortening_hook_detail(self):
        key = "sk_live_" + "Z" * 24
        for padding in (0, 63):
            with self.subTest(padding=padding), TemporaryDirectory() as temp:
                root = Path(temp)
                command = "echo " + ("x" * padding) + " " + key + " || true"
                hooks = {"PostToolUse": [{"hooks": [{"type": "command", "command": command}]}]}
                findings = check_hooks(root, ".claude/settings.json", hooks)
                for fmt in ("md", "json", "github", "sarif"):
                    with self.subTest(format=fmt):
                        self.assertNotIn("sk_live_Z", render(fmt, root, findings, False))

    def test_agent_skills_name_separator(self):
        for name, expected in (("lint-local", False), ("lint--local", True)):
            with self.subTest(name=name, expected=expected), TemporaryDirectory() as temp:
                root = Path(temp)
                skill = root / ".claude/skills" / name / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text(f"---\nname: {name}\ndescription: Lint files.\n---\n")
                self.assertEqual(bool(check_skills(root)), expected)


if __name__ == "__main__":
    unittest.main()
