from __future__ import annotations

import json
import os
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

    def test_reinstall_preserves_unrelated_handler_in_same_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            behavior_hooks.install(root)
            hooks_path = root / ".codex" / "hooks.json"
            payload = json.loads(hooks_path.read_text(encoding="utf-8"))
            payload["hooks"]["SessionStart"][0]["hooks"].append(
                {"type": "command", "command": "echo keep-me"}
            )
            hooks_path.write_text(json.dumps(payload), encoding="utf-8")
            behavior_hooks.install(root)
            installed = json.loads(hooks_path.read_text(encoding="utf-8"))
            commands = [
                item.get("command")
                for group in installed["hooks"]["SessionStart"]
                for item in group["hooks"]
            ]
            self.assertIn("echo keep-me", commands)

    def test_interrupt_and_session_end_use_supported_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            behavior_hooks.install(root)
            payload = json.loads((root / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            for event in ("Interrupt", "SessionEnd"):
                monitor = next(
                    item
                    for group in payload["hooks"][event]
                    for item in group["hooks"]
                    if behavior_hooks.is_ours(item)
                )
                self.assertEqual(monitor["timeout"], 3)

    @unittest.skipIf(os.name == "nt", "POSIX mode bits are not authoritative on Windows")
    def test_hash_key_is_owner_only_on_posix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            behavior_hooks.install(root)
            mode = (root / ".codex" / "behavior-monitor.key").stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)

    def test_remove_deletes_monitor_only_hook_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            behavior_hooks.install(root)
            behavior_hooks.remove(root)
            self.assertFalse((root / ".codex" / "hooks.json").exists())


if __name__ == "__main__":
    unittest.main()
