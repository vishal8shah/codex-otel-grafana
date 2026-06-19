import datetime as dt
import importlib.util
import pathlib
import sys
import unittest


TOOL_DIR = pathlib.Path(__file__).parents[1]
MODULE_PATH = TOOL_DIR / "tool_failure.py"
SPEC = importlib.util.spec_from_file_location("tool_failure", MODULE_PATH)
tool_failure = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = tool_failure
SPEC.loader.exec_module(tool_failure)

TRIGGER_PATH = TOOL_DIR / "synthetic_trigger.py"
TRIGGER_SPEC = importlib.util.spec_from_file_location("tool_failure_trigger", TRIGGER_PATH)
synthetic_trigger = importlib.util.module_from_spec(TRIGGER_SPEC)
assert TRIGGER_SPEC.loader is not None
sys.modules[TRIGGER_SPEC.name] = synthetic_trigger
TRIGGER_SPEC.loader.exec_module(synthetic_trigger)


NOW = dt.datetime(2026, 6, 19, 1, 0, tzinfo=dt.timezone.utc)


def event(name, *, success=None, duration_ms=None, seconds=0):
    return {
        "run_hash": "a" * 64,
        "tool_name": "fixture_tool",
        "timestamp": NOW + dt.timedelta(seconds=seconds),
        "event_name": name,
        "success": success,
        "duration_ms": duration_ms,
    }


def classify(*events):
    aggregate = tool_failure.aggregate_events(events)[0]
    return tool_failure.classify_tool(aggregate, 360)


class ToolFailureTests(unittest.TestCase):
    def test_failed_result(self):
        row = classify(
            event(tool_failure.TOOL_DECISION_EVENT),
            event(tool_failure.TOOL_RESULT_EVENT, success=False, duration_ms=750, seconds=1),
        )
        self.assertEqual(row["state"], tool_failure.FAILED_RESULT)
        self.assertEqual(row["result_state"], "failed")
        self.assertEqual(row["failed_results"], 1)
        self.assertEqual(row["latest_duration_ms"], 750)

    def test_successful_result(self):
        row = classify(
            event(tool_failure.TOOL_DECISION_EVENT),
            event(tool_failure.TOOL_RESULT_EVENT, success=True, duration_ms=25, seconds=1),
        )
        self.assertEqual(row["state"], tool_failure.SUCCESSFUL_RESULT)
        self.assertEqual(row["successful_results"], 1)

    def test_selected_no_result(self):
        row = classify(event(tool_failure.TOOL_DECISION_EVENT))
        self.assertEqual(row["state"], tool_failure.SELECTED_NO_RESULT)
        self.assertEqual(row["result_count"], 0)

    def test_unknown_result(self):
        row = classify(event(tool_failure.TOOL_RESULT_EVENT, success=None))
        self.assertEqual(row["state"], tool_failure.UNKNOWN_RESULT)
        self.assertEqual(row["unknown_results"], 1)

    def test_failure_wins_when_success_and_failure_are_both_observed(self):
        row = classify(
            event(tool_failure.TOOL_RESULT_EVENT, success=True),
            event(tool_failure.TOOL_RESULT_EVENT, success=False, seconds=1),
        )
        self.assertEqual(row["state"], tool_failure.FAILED_RESULT)
        self.assertEqual(row["result_count"], 2)

    def test_hmac_hash_is_stable_and_private(self):
        first = tool_failure.hash_run_identifier("private-fixture-id", "fixture-key")
        second = tool_failure.hash_run_identifier("private-fixture-id", "fixture-key")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotIn("private-fixture-id", first)

    def test_loki_input_is_allowlisted_and_source_labels_are_cleared(self):
        labels = {
            "conversation_id": "private-fixture-id",
            "event_name": "codex.tool_result",
            "tool_name": "fixture_tool",
            "success": "false",
            "duration_ms": "500",
            "call_id": "private-call-id",
            "arguments": "private-arguments",
            "output": "private-output",
            "cwd": "private-path",
        }
        response = {
            "data": {
                "result": [
                    {
                        "stream": labels,
                        "values": [["1781830800000000000", "ignored raw body"]],
                    }
                ]
            }
        }
        events, count = tool_failure.safe_events_from_loki(response, "fixture-key")
        self.assertEqual(count, 1)
        self.assertEqual(labels, {})
        self.assertEqual(
            set(events[0]),
            {"run_hash", "tool_name", "timestamp", "event_name", "success", "duration_ms"},
        )
        serialized = str(events)
        for private in (
            "private-fixture-id",
            "private-call-id",
            "private-arguments",
            "private-output",
            "private-path",
        ):
            self.assertNotIn(private, serialized)

    def test_emission_rejects_non_log_endpoint(self):
        payload = tool_failure.build_otlp_logs([], NOW)
        with self.assertRaises(RuntimeError):
            tool_failure.assert_log_only_emission(
                "http://localhost:4318/v1/metrics", payload
            )

    def test_synthetic_trigger_is_raw_logs_only_and_correlated(self):
        payload = synthetic_trigger.build_synthetic_payload(
            NOW, "synthetic-tool-failure-fixture"
        )
        synthetic_trigger.validate_payload("http://localhost:4318/v1/logs", payload)
        records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        self.assertEqual(len(records), 2)
        attributes = [
            {
                item["key"]: next(iter(item["value"].values()))
                for item in record["attributes"]
            }
            for record in records
        ]
        self.assertEqual(
            {item["event_name"] for item in attributes},
            {"codex.tool_decision", "codex.tool_result"},
        )
        self.assertEqual(len({item["conversation_id"] for item in attributes}), 1)
        self.assertEqual(len({item["synthetic.run_id"] for item in attributes}), 1)
        serialized = str(payload)
        self.assertNotIn("codex.tool_diagnostic", serialized)
        self.assertNotIn("resourceMetrics", serialized)

    def test_summary_contains_safe_fields_only(self):
        row = classify(
            event(tool_failure.TOOL_DECISION_EVENT),
            event(tool_failure.TOOL_RESULT_EVENT, success=False, seconds=1),
        )
        summary = tool_failure.format_summary([row], 360)
        self.assertIn("Failed results: 1", summary)
        self.assertIn("tool_name=fixture_tool", summary)
        self.assertIn("run_hash=" + "a" * 64, summary)
        for unsafe in ("conversation_id", "call_id", "arguments=", "output=", "cwd="):
            self.assertNotIn(unsafe, summary)


if __name__ == "__main__":
    unittest.main()
