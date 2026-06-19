import datetime as dt
import importlib.util
import pathlib
import sys
import unittest


TOOL_DIR = pathlib.Path(__file__).parents[1]
MODULE_PATH = TOOL_DIR / "slow_contributor.py"
SPEC = importlib.util.spec_from_file_location("slow_contributor", MODULE_PATH)
slow_contributor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = slow_contributor
SPEC.loader.exec_module(slow_contributor)

TRIGGER_PATH = TOOL_DIR / "synthetic_trigger.py"
TRIGGER_SPEC = importlib.util.spec_from_file_location("slow_contributor_trigger", TRIGGER_PATH)
synthetic_trigger = importlib.util.module_from_spec(TRIGGER_SPEC)
assert TRIGGER_SPEC.loader is not None
sys.modules[TRIGGER_SPEC.name] = synthetic_trigger
TRIGGER_SPEC.loader.exec_module(synthetic_trigger)


NOW = dt.datetime(2026, 6, 19, 8, 0, tzinfo=dt.timezone.utc)


def event(kind, *, duration_ms, run="a", endpoint="b", tool="", seconds=0):
    return {
        "run_hash": run * 64,
        "contributor_type": kind,
        "endpoint_hash": endpoint * 64 if kind == "api_request" else "",
        "tool_name": tool if kind == "tool_result" else "",
        "duration_ms": duration_ms,
        "timestamp": NOW + dt.timedelta(seconds=seconds),
    }


def rows(*events, api_ms=10_000, tool_ms=10_000):
    return slow_contributor.classify_contributors(
        slow_contributor.aggregate_events(events), 360, api_ms, tool_ms
    )


class SlowContributorTests(unittest.TestCase):
    def test_slow_api_contributor(self):
        result = rows(event("api_request", duration_ms=10_001))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["state"], slow_contributor.SLOW_API_CONTRIBUTOR)
        self.assertEqual(result[0]["grouping_precision"], "run_endpoint")

    def test_slow_tool_contributor(self):
        result = rows(event("tool_result", duration_ms=10_001, tool="fixture_tool"))
        self.assertEqual(result[0]["state"], slow_contributor.SLOW_TOOL_CONTRIBUTOR)
        self.assertEqual(result[0]["grouping_precision"], "run_tool")

    def test_multiple_slow_contributors_for_same_run(self):
        result = rows(
            event("api_request", duration_ms=15_000),
            event("tool_result", duration_ms=12_000, tool="fixture_tool", seconds=1),
        )
        self.assertEqual(len(result), 2)
        self.assertEqual({row["state"] for row in result}, {slow_contributor.MULTIPLE_SLOW_CONTRIBUTORS})

    def test_thresholds_are_configurable_and_strict(self):
        self.assertEqual(rows(event("api_request", duration_ms=10_000)), [])
        self.assertEqual(len(rows(event("api_request", duration_ms=5_001), api_ms=5_000)), 1)

    def test_group_uses_max_duration(self):
        result = rows(
            event("api_request", duration_ms=100),
            event("api_request", duration_ms=15_000, seconds=1),
        )
        self.assertEqual(result[0]["duration_ms"], 15_000)
        self.assertEqual(result[0]["event_count"], 2)

    def test_hmac_hash_is_stable_and_private(self):
        first = slow_contributor.hash_identifier("private-value", "fixture-key")
        second = slow_contributor.hash_identifier("private-value", "fixture-key")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotIn("private-value", first)

    def test_loki_input_is_allowlisted_and_source_labels_are_cleared(self):
        api_labels = {
            "conversation_id": "private-run",
            "endpoint": "private-endpoint",
            "event_name": "codex.api_request",
            "duration_ms": "15000",
            "prompt": "private-prompt",
            "user_email": "private-email",
        }
        tool_labels = {
            "conversation_id": "private-run",
            "event_name": "codex.tool_result",
            "duration_ms": "12000",
            "tool_name": "fixture_tool",
            "call_id": "private-call",
            "arguments": "private-arguments",
            "output": "private-output",
            "cwd": "private-path",
        }
        response = {"data": {"result": [
            {"stream": api_labels, "values": [["1781856000000000000", "ignored"]]},
            {"stream": tool_labels, "values": [["1781856001000000000", "ignored"]]},
        ]}}
        events, count = slow_contributor.safe_events_from_loki(response, "fixture-key")
        self.assertEqual(count, 2)
        self.assertEqual(api_labels, {})
        self.assertEqual(tool_labels, {})
        self.assertEqual(
            set(events[0]),
            {"run_hash", "contributor_type", "endpoint_hash", "tool_name", "duration_ms", "timestamp"},
        )
        serialized = str(events)
        for private in ("private-run", "private-endpoint", "private-prompt", "private-email", "private-call", "private-arguments", "private-output", "private-path"):
            self.assertNotIn(private, serialized)

    def test_unconfirmed_ttft_is_ignored(self):
        labels = {
            "conversation_id": "private-run",
            "event_name": "codex.turn_ttft",
            "duration_ms": "20000",
        }
        response = {"data": {"result": [{"stream": labels, "values": [["1781856000000000000", "ignored"]]}]}}
        events, count = slow_contributor.safe_events_from_loki(response, "fixture-key")
        self.assertEqual(events, [])
        self.assertEqual(count, 0)
        self.assertEqual(labels, {})

    def test_emission_rejects_non_log_endpoint(self):
        payload = slow_contributor.build_otlp_logs([], NOW)
        with self.assertRaises(RuntimeError):
            slow_contributor.assert_log_only_emission("http://localhost:4318/v1/metrics", payload)

    def test_synthetic_trigger_emits_raw_confirmed_logs_only(self):
        payload = synthetic_trigger.build_synthetic_payload(NOW, "synthetic-slow-contributor-fixture")
        synthetic_trigger.validate_payload("http://localhost:4318/v1/logs", payload)
        records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        self.assertEqual(len(records), 2)
        attrs = [{item["key"]: next(iter(item["value"].values())) for item in record["attributes"]} for record in records]
        self.assertEqual({item["event_name"] for item in attrs}, {"codex.api_request", "codex.tool_result"})
        self.assertEqual(len({item["conversation_id"] for item in attrs}), 1)
        serialized = str(payload)
        self.assertNotIn("codex.slow_contributor", serialized)
        self.assertNotIn("resourceMetrics", serialized)

    def test_summary_has_nonclaim_and_safe_fields(self):
        result = rows(event("api_request", duration_ms=15_000))
        summary = slow_contributor.format_summary(result, 360, 10_000, 10_000)
        self.assertIn("does not measure full end-to-end Codex turn latency", summary)
        self.assertIn("run_hash=" + "a" * 64, summary)
        for unsafe in ("conversation_id", "endpoint=", "call_id", "arguments", "output="):
            self.assertNotIn(unsafe, summary)


if __name__ == "__main__":
    unittest.main()
