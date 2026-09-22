from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


TOOL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import behavior_analyze
from behavior_analyze import correlate, observations_from_loki
from behavior_common import ANALYZER_HEARTBEAT_EVENT, load_policy


POLICY = load_policy(TOOL_ROOT / "policy.json")
NOW = dt.datetime(2026, 9, 17, tzinfo=dt.timezone.utc)


def observation(
    signal: str,
    *,
    index: int = 0,
    action: str = "observed",
    severity: str = "medium",
    tool_class: str = "shell",
    hook_event: str | None = None,
):
    rule = next(item for item in POLICY["rules"] if item["signal"] == signal)
    timestamp = NOW + dt.timedelta(seconds=index)
    return {
        "schema_version": 1,
        "run_hash": "a" * 64,
        "turn_hash": "b" * 64,
        "hook_event": hook_event or ("SubagentStart" if signal == "subagent_activity" else "PreToolUse"),
        "tool_class": tool_class,
        "behavior_signal": signal,
        "policy_rule_id": rule["id"],
        "severity": severity,
        "policy_mode": "observe",
        "policy_action": action,
        "permission_mode": "default",
        "synthetic": True,
        "evidence_source": "synthetic_hook_fixture",
        "observed_at": timestamp.isoformat().replace("+00:00", "Z"),
        "signal_count": 1,
        "timestamp": timestamp,
    }


class BehaviorAnalyzeTests(unittest.TestCase):
    def test_recon_to_sensitive_and_credential_egress(self):
        rows = [
            observation("environment_reconnaissance", index=0),
            observation("sensitive_resource_probe", index=1, severity="high"),
            observation("external_write", index=2, severity="high"),
        ]
        categories = {row["category"] for row in correlate(rows, POLICY)}
        self.assertIn("recon_to_sensitive_probe", categories)
        self.assertIn("credential_to_egress", categories)
        self.assertIn("multi_category_escalation", categories)

    def test_repeated_denial_and_blocked_state(self):
        rows = [observation("destructive_filesystem_action", index=i, action="denied", severity="critical") for i in range(2)]
        repeated = next(row for row in correlate(rows, POLICY) if row["category"] == "repeated_denial")
        self.assertEqual(repeated["state"], "BLOCKED")

    def test_subagent_burst_and_high_risk_sequence(self):
        rows = [observation("subagent_activity", index=i, severity="info", tool_class="subagent") for i in range(4)]
        rows.append(observation("destructive_filesystem_action", index=5, action="denied", severity="critical"))
        categories = {row["category"] for row in correlate(rows, POLICY)}
        self.assertIn("subagent_burst", categories)
        self.assertIn("subagent_high_risk_sequence", categories)

    def test_persistence_network_sequence(self):
        rows = [observation("persistence_creation", index=0, severity="critical"), observation("external_write", index=1, severity="high")]
        finding = next(row for row in correlate(rows, POLICY) if row["category"] == "persistence_network_sequence")
        self.assertEqual(finding["severity"], "critical")

    def test_boundary_to_destructive_sequence_and_window(self):
        inside = [
            observation("workspace_boundary_attempt", index=0, severity="high"),
            observation("destructive_filesystem_action", index=300, severity="critical"),
        ]
        outside = [
            observation("workspace_boundary_attempt", index=0, severity="high"),
            observation("destructive_filesystem_action", index=301, severity="critical"),
        ]
        self.assertIn("destructive_sequence", {row["category"] for row in correlate(inside, POLICY)})
        self.assertNotIn("destructive_sequence", {row["category"] for row in correlate(outside, POLICY)})

    def test_subagent_sequence_requires_configured_burst(self):
        below = [observation("subagent_activity", index=i, severity="info", tool_class="subagent") for i in range(3)]
        below.append(observation("destructive_filesystem_action", index=4, action="denied", severity="critical"))
        self.assertNotIn("subagent_high_risk_sequence", {row["category"] for row in correlate(below, POLICY)})

    def test_subagent_stops_do_not_inflate_fanout(self):
        rows = [
            observation("subagent_activity", index=0, severity="info", tool_class="subagent", hook_event="SubagentStart"),
            observation("subagent_activity", index=1, severity="info", tool_class="subagent", hook_event="SubagentStop"),
            observation("subagent_activity", index=2, severity="info", tool_class="subagent", hook_event="SubagentStart"),
            observation("subagent_activity", index=3, severity="info", tool_class="subagent", hook_event="SubagentStop"),
        ]
        self.assertNotIn("subagent_burst", {row["category"] for row in correlate(rows, POLICY)})

    def test_unusual_tool_volume_threshold(self):
        rows = [observation("tool_activity", index=i, severity="info") for i in range(POLICY["thresholds"]["unusual_tool_volume"])]
        self.assertIn("unusual_tool_volume", {row["category"] for row in correlate(rows, POLICY)})

    def test_repeated_failure_threshold(self):
        rows = [observation("tool_activity", index=i, action="failed", severity="info") for i in range(3)]
        self.assertIn("repeated_failure", {row["category"] for row in correlate(rows, POLICY)})

    def test_loki_parser_allowlists_fields(self):
        response = {
            "data": {"result": [{
                "stream": {
                    "run_hash": "a" * 64,
                    "behavior_signal": "tool_activity",
                    "policy_action": "allowed",
                    "severity": "info",
                    "synthetic": "true",
                    "arguments": "must-not-pass",
                    "output": "must-not-pass",
                },
                "values": [[str(int(NOW.timestamp() * 1_000_000_000)), ""]],
            }]}
        }
        rows, count = observations_from_loki(response)
        self.assertEqual(count, 1)
        self.assertNotIn("arguments", rows[0])
        self.assertNotIn("output", rows[0])

    def test_findings_are_deterministic_and_privacy_safe(self):
        rows = [observation("destructive_filesystem_action", action="denied", severity="critical")]
        first = correlate(rows, POLICY)
        second = correlate(rows, POLICY)
        self.assertEqual(first, second)
        serialized = str(first)
        for forbidden in ("command", "arguments", "output", "session_id", "turn_id", "tool_input", "tool_response"):
            self.assertNotIn(forbidden, serialized)

    def test_rejects_raw_or_malformed_observation_identifiers(self):
        row = observation("destructive_filesystem_action", action="denied", severity="critical")
        row["run_hash"] = r"raw/C:\Users\Alice"
        with self.assertRaisesRegex(ValueError, "run hash"):
            correlate([row], POLICY)

    def test_emit_derived_writes_analyzer_heartbeat_even_without_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = pathlib.Path(directory) / "observations.json"
            fixture.write_text(json.dumps([]), encoding="utf-8")
            emitted = []
            with mock.patch.object(behavior_analyze, "post_otlp", side_effect=lambda url, payload: emitted.append(payload)):
                result = behavior_analyze.main(["--observations-json", str(fixture), "--emit-derived"])
            self.assertEqual(result, 0)
            self.assertEqual(len(emitted), 1)
            scope = emitted[0]["resourceLogs"][0]["scopeLogs"][0]
            self.assertEqual(scope["scope"]["name"], ANALYZER_HEARTBEAT_EVENT)

    def test_malformed_fixture_row_fails_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = pathlib.Path(directory) / "observations.json"
            fixture.write_text(json.dumps(["raw unexpected value"]), encoding="utf-8")
            self.assertEqual(behavior_analyze.main(["--observations-json", str(fixture), "--dry-run"]), 1)


if __name__ == "__main__":
    unittest.main()
