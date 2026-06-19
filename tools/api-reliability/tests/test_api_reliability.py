import datetime as dt
import importlib.util
import pathlib
import sys
import unittest


TOOL_DIR = pathlib.Path(__file__).parents[1]
MODULE_PATH = TOOL_DIR / "api_reliability.py"
SPEC = importlib.util.spec_from_file_location("api_reliability", MODULE_PATH)
api_reliability = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = api_reliability
SPEC.loader.exec_module(api_reliability)

TRIGGER_PATH = TOOL_DIR / "synthetic_trigger.py"
TRIGGER_SPEC = importlib.util.spec_from_file_location("api_reliability_trigger", TRIGGER_PATH)
synthetic_trigger = importlib.util.module_from_spec(TRIGGER_SPEC)
assert TRIGGER_SPEC.loader is not None
sys.modules[TRIGGER_SPEC.name] = synthetic_trigger
TRIGGER_SPEC.loader.exec_module(synthetic_trigger)


NOW = dt.datetime(2026, 6, 19, 6, 0, tzinfo=dt.timezone.utc)


def event(*, success=None, duration_ms=None, attempt=None, bucket="unknown", seconds=0):
    return {
        "run_hash": "a" * 64,
        "endpoint_hash": "b" * 64,
        "timestamp": NOW + dt.timedelta(seconds=seconds),
        "success": success,
        "duration_ms": duration_ms,
        "attempt": attempt,
        "status_bucket": bucket,
    }


def classify(*events, threshold=10_000):
    aggregate = api_reliability.aggregate_events(events)[0]
    return api_reliability.classify_api(aggregate, 360, threshold)


class ApiReliabilityTests(unittest.TestCase):
    def test_failed_request(self):
        row = classify(event(success=False, duration_ms=500, attempt=1, bucket="5xx"))
        self.assertEqual(row["state"], api_reliability.FAILED_REQUEST)
        self.assertEqual(row["failed_evidence_count"], 1)
        self.assertEqual(row["status_bucket"], "5xx")

    def test_retried_request(self):
        row = classify(event(success=True, duration_ms=500, attempt=2, bucket="2xx"))
        self.assertEqual(row["state"], api_reliability.RETRIED_REQUEST)
        self.assertTrue(row["retry_observed"])

    def test_slow_request(self):
        row = classify(event(success=True, duration_ms=10_001, attempt=1, bucket="2xx"))
        self.assertEqual(row["state"], api_reliability.SLOW_REQUEST)
        self.assertTrue(row["slow_observed"])

    def test_successful_request(self):
        row = classify(event(success=True, duration_ms=100, attempt=1, bucket="2xx"))
        self.assertEqual(row["state"], api_reliability.SUCCESSFUL_REQUEST)

    def test_unknown_request(self):
        row = classify(event(duration_ms=100, attempt=1))
        self.assertEqual(row["state"], api_reliability.UNKNOWN_REQUEST)
        self.assertEqual(row["unknown_outcome_count"], 1)

    def test_state_precedence(self):
        failed = event(success=False, duration_ms=20_000, attempt=3, bucket="5xx")
        self.assertEqual(classify(failed)["state"], api_reliability.FAILED_REQUEST)
        retried = event(success=True, duration_ms=20_000, attempt=2, bucket="2xx")
        self.assertEqual(classify(retried)["state"], api_reliability.RETRIED_REQUEST)

    def test_status_code_can_supply_outcome_evidence(self):
        self.assertEqual(classify(event(bucket="4xx"))["state"], api_reliability.FAILED_REQUEST)
        self.assertEqual(classify(event(bucket="2xx"))["state"], api_reliability.SUCCESSFUL_REQUEST)

    def test_hmac_hash_is_stable_and_private(self):
        first = api_reliability.hash_identifier("private-value", "fixture-key")
        second = api_reliability.hash_identifier("private-value", "fixture-key")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotIn("private-value", first)

    def test_loki_input_is_allowlisted_and_source_labels_are_cleared(self):
        labels = {
            "conversation_id": "private-run",
            "endpoint": "private-endpoint",
            "event_name": "codex.api_request",
            "duration_ms": "12500",
            "http_response_status_code": "503",
            "success": "false",
            "attempt": "2",
            "prompt": "private-prompt",
            "cwd": "private-path",
            "tool_output": "private-output",
        }
        response = {"data": {"result": [{"stream": labels, "values": [["1781848800000000000", "ignored raw body"]]}]}}
        events, count = api_reliability.safe_events_from_loki(response, "fixture-key")
        self.assertEqual(count, 1)
        self.assertEqual(labels, {})
        self.assertEqual(
            set(events[0]),
            {"run_hash", "endpoint_hash", "timestamp", "success", "duration_ms", "attempt", "status_bucket"},
        )
        serialized = str(events)
        for private in ("private-run", "private-endpoint", "private-prompt", "private-path", "private-output"):
            self.assertNotIn(private, serialized)

    def test_emission_rejects_non_log_endpoint(self):
        payload = api_reliability.build_otlp_logs([], NOW)
        with self.assertRaises(RuntimeError):
            api_reliability.assert_log_only_emission("http://localhost:4318/v1/metrics", payload)

    def test_synthetic_trigger_emits_raw_api_logs_only(self):
        payload = synthetic_trigger.build_synthetic_payload(NOW, "synthetic-api-reliability-fixture")
        synthetic_trigger.validate_payload("http://localhost:4318/v1/logs", payload)
        records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        self.assertEqual(len(records), 2)
        attributes = [
            {item["key"]: next(iter(item["value"].values())) for item in record["attributes"]}
            for record in records
        ]
        self.assertEqual({item["event_name"] for item in attributes}, {"codex.api_request"})
        self.assertEqual(len({item["conversation_id"] for item in attributes}), 1)
        self.assertEqual(len({item["endpoint"] for item in attributes}), 1)
        self.assertEqual({item["attempt"] for item in attributes}, {"1", "2"})
        serialized = str(payload)
        self.assertNotIn("codex.api_diagnostic", serialized)
        self.assertNotIn("resourceMetrics", serialized)

    def test_summary_contains_safe_fields_only(self):
        row = classify(event(success=False, duration_ms=12_500, attempt=2, bucket="5xx"))
        summary = api_reliability.format_summary([row], 360, 10_000)
        self.assertIn("Failed groups: 1", summary)
        self.assertIn("Groups with retry evidence: 1", summary)
        self.assertIn("Groups over the slow threshold: 1", summary)
        self.assertIn("endpoint_hash=" + "b" * 64, summary)
        for unsafe in ("conversation_id", "endpoint=", "prompt", "cwd=", "arguments", "output="):
            self.assertNotIn(unsafe, summary)


if __name__ == "__main__":
    unittest.main()
