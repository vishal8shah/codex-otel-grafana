from __future__ import annotations

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
PROVISIONING = ROOT / "observability" / "provisioning" / "alerting" / "stuck-notification.yaml"


class AlertProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(PROVISIONING.read_text(encoding="utf-8"))
        cls.rule = cls.payload["groups"][0]["rules"][0]

    def test_uses_only_derived_stuck_stream_and_dedupes_by_run_hash(self) -> None:
        query = self.rule["data"][0]["model"]["expr"]
        self.assertIn('service_name="Codex Run Health"', query)
        self.assertIn('event_name="codex.run_health"', query)
        self.assertIn('state="STUCK_CANDIDATE"', query)
        self.assertIn("sum by (run_hash, state)", query)
        self.assertIn("[2m]", query)

    def test_groups_and_suppresses_repeated_notifications(self) -> None:
        settings = self.rule["notification_settings"]
        self.assertIn("run_hash", settings["group_by"])
        self.assertEqual(settings["repeat_interval"], "4h")
        self.assertEqual(settings["receiver"], "Codex local dev webhook")

    def test_keeps_unsafe_fields_and_native_metrics_out(self) -> None:
        serialized = json.dumps(self.payload).lower()
        for unsafe in (
            "conversation_id",
            "call_id",
            "raw_endpoint",
            "tool arguments",
            "tool output",
            "user_email",
        ):
            self.assertNotIn(unsafe, serialized)
        self.assertNotIn("resourcemetrics", serialized)


if __name__ == "__main__":
    unittest.main()
