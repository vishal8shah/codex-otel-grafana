from __future__ import annotations

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "dev_webhook_listener.py"
SPEC = importlib.util.spec_from_file_location("dev_webhook_listener", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SafeNotificationTests(unittest.TestCase):
    def test_extracts_only_safe_alert_fields(self) -> None:
        run_hash = "a" * 64
        record = MODULE.safe_notification(
            {
                "status": "firing",
                "alerts": [
                    {
                        "status": "firing",
                        "labels": {
                            "alertname": "Codex stuck candidate detected",
                            "run_hash": run_hash,
                            "state": "STUCK_CANDIDATE",
                        },
                        "annotations": {"summary": "safe but deliberately not copied"},
                    }
                ],
            }
        )
        self.assertEqual(record["alert_count"], 1)
        self.assertEqual(record["alerts"][0]["run_hash"], run_hash)
        self.assertNotIn("annotations", record)

    def test_rejects_unsafe_nested_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "conversation_id"):
            MODULE.safe_notification(
                {"status": "firing", "alerts": [], "extra": {"conversation_id": "raw"}}
            )

    def test_rejects_non_hash_run_identifier(self) -> None:
        with self.assertRaisesRegex(ValueError, "privacy-safe hash"):
            MODULE.safe_notification(
                {"status": "firing", "alerts": [{"labels": {"run_hash": "raw-id"}}]}
            )


if __name__ == "__main__":
    unittest.main()
