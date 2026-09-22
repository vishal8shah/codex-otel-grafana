from __future__ import annotations

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
PROVISIONING = ROOT / "observability" / "provisioning" / "alerting" / "stuck-notification.yaml"
BEHAVIOR_PROVISIONING = ROOT / "observability" / "provisioning" / "alerting" / "behavior-notification.yaml"


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


class BehaviorAlertProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(BEHAVIOR_PROVISIONING.read_text(encoding="utf-8"))
        cls.rule = cls.payload["groups"][0]["rules"][0]

    def test_uses_only_privacy_safe_high_risk_findings(self) -> None:
        query = self.rule["data"][0]["model"]["expr"]
        self.assertIn('service_name="Codex Agent Behavior Diagnosis"', query)
        self.assertIn('event_name="codex.behavior_finding"', query)
        self.assertIn('severity=~"high|critical"', query)
        self.assertIn("sum by (run_hash, finding_id, category, severity, state)", query)

    def test_routes_to_local_receiver_and_deduplicates(self) -> None:
        settings = self.rule["notification_settings"]
        self.assertEqual(settings["receiver"], "Codex local dev webhook")
        self.assertIn("finding_id", settings["group_by"])
        self.assertEqual(settings["repeat_interval"], "4h")

    def test_alert_states_do_not_claim_silence_is_health(self) -> None:
        self.assertEqual(self.rule["noDataState"], "OK")
        self.assertEqual(self.rule["execErrState"], "Error")
        self.assertIn("not proof", self.rule["annotations"]["summary"])


if __name__ == "__main__":
    unittest.main()
