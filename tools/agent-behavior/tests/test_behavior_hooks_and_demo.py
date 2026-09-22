from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest


TOOL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import behavior_demo
import behavior_hooks
from behavior_analyze import correlate
from behavior_common import load_policy


class BehaviorHooksAndDemoTests(unittest.TestCase):
    def test_install_check_remove_preserves_unrelated_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            config = root / ".codex"
            config.mkdir()
            original = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo existing"}]}]}}
            (config / "hooks.json").write_text(json.dumps(original), encoding="utf-8")
            behavior_hooks.install(root)
            self.assertEqual(behavior_hooks.check(root), 0)
            installed = json.loads((config / "hooks.json").read_text(encoding="utf-8"))
            self.assertTrue(any(item.get("command") == "echo existing" for group in installed["hooks"]["SessionStart"] for item in group["hooks"]))
            monitor_handler = next(item for group in installed["hooks"]["PreToolUse"] for item in group["hooks"] if behavior_hooks.is_ours(item))
            self.assertIn(str(pathlib.Path(sys.executable).resolve()), monitor_handler["command"])
            self.assertIn(str(pathlib.Path(sys.executable).resolve()), monitor_handler["command_windows"])
            self.assertNotIn("UserPromptSubmit", installed["hooks"])
            behavior_hooks.remove(root)
            removed = json.loads((config / "hooks.json").read_text(encoding="utf-8"))
            self.assertTrue(any(item.get("command") == "echo existing" for group in removed["hooks"]["SessionStart"] for item in group["hooks"]))
            self.assertFalse((config / "behavior-monitor.key").exists())

    def test_incident_safe_profile_has_required_evidence(self):
        policy = load_policy(TOOL_ROOT / "policy.json")
        observations = behavior_demo.build_observations(policy)
        findings = correlate(observations, policy)
        self.assertEqual(len(observations), 24)
        self.assertTrue(any(row["policy_action"] == "denied" for row in observations))
        self.assertIn("multi_category_escalation", {row["category"] for row in findings})
        self.assertIn("destructive_sequence", {row["category"] for row in findings})
        self.assertTrue(all(row["synthetic"] for row in observations))

    def test_remove_deletes_monitor_only_hook_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            behavior_hooks.install(root)
            behavior_hooks.remove(root)
            self.assertFalse((root / ".codex" / "hooks.json").exists())


if __name__ == "__main__":
    unittest.main()
