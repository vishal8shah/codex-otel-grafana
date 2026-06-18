import datetime as dt
import importlib.util
import pathlib
import sys
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "run_health.py"
SPEC = importlib.util.spec_from_file_location("run_health", MODULE_PATH)
run_health = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = run_health
SPEC.loader.exec_module(run_health)

TRIGGER_PATH = pathlib.Path(__file__).parents[1] / "synthetic_trigger.py"
TRIGGER_SPEC = importlib.util.spec_from_file_location("synthetic_trigger", TRIGGER_PATH)
synthetic_trigger = importlib.util.module_from_spec(TRIGGER_SPEC)
assert TRIGGER_SPEC.loader is not None
sys.modules[TRIGGER_SPEC.name] = synthetic_trigger
TRIGGER_SPEC.loader.exec_module(synthetic_trigger)


NOW = dt.datetime(2026, 6, 18, 12, 0, tzinfo=dt.timezone.utc)


def aggregate(*, quiet: int, meaningful: bool = True):
    timestamp = NOW - dt.timedelta(seconds=quiet)
    return run_health.RunAggregate(
        run_hash="a" * 64,
        first_seen=timestamp - dt.timedelta(minutes=5),
        last_seen=timestamp,
        last_event="codex.api_request" if meaningful else "unknown",
        model="fixture-model",
        event_count=2,
        meaningful_activity=meaningful,
    )


def classify(run):
    return run_health.classify_run(run, NOW, 120, 600, 360)


class StateModelTests(unittest.TestCase):
    def test_completed_recently(self):
        run = aggregate(quiet=30)
        run.completed = True
        self.assertEqual(classify(run)["state"], run_health.COMPLETED_RECENTLY)

    def test_slow_but_alive(self):
        self.assertEqual(classify(aggregate(quiet=60))["state"], run_health.SLOW_BUT_ALIVE)

    def test_stuck_candidate(self):
        self.assertEqual(classify(aggregate(quiet=900))["state"], run_health.STUCK_CANDIDATE)

    def test_unknown_incomplete(self):
        self.assertEqual(
            classify(aggregate(quiet=300, meaningful=False))["state"],
            run_health.UNKNOWN_INCOMPLETE,
        )

    def test_hmac_hash_is_stable_and_does_not_reveal_input(self):
        first = run_health.hash_run_identifier("fixture-run", "fixture-key")
        second = run_health.hash_run_identifier("fixture-run", "fixture-key")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotIn("fixture-run", first)

    def test_loki_input_is_allowlisted_and_source_labels_are_cleared(self):
        labels = {
            "conversation_id": "fixture-private-id",
            "event_name": "codex.api_request",
            "model": "fixture-model",
            "arguments": "fixture-private-arguments",
            "output": "fixture-private-output",
            "user_email": "private-placeholder",
        }
        response = {
            "data": {
                "result": [
                    {
                        "stream": labels,
                        "values": [["1781784000000000000", "ignored raw log body"]],
                    }
                ]
            }
        }
        events, count = run_health.safe_events_from_loki(response, "fixture-key")
        self.assertEqual(count, 1)
        self.assertEqual(labels, {})
        self.assertEqual(
            set(events[0]),
            {
                "run_hash",
                "timestamp",
                "event_name",
                "event_kind",
                "model",
            },
        )
        self.assertNotIn("fixture-private-id", str(events))
        self.assertNotIn("fixture-private-output", str(events))

    def test_emission_rejects_non_log_endpoint(self):
        payload = run_health.build_otlp_logs([], NOW)
        with self.assertRaises(RuntimeError):
            run_health.assert_log_only_emission("http://localhost:4318/v1/metrics", payload)

    def test_synthetic_trigger_emits_source_logs_not_derived_rows_or_metrics(self):
        payload = synthetic_trigger.build_synthetic_payload(NOW, "synthetic-stuck-fixture", 660)
        synthetic_trigger.validate_payload("http://localhost:4318/v1/logs", payload)
        serialized = str(payload)
        self.assertIn("codex.conversation_starts", serialized)
        self.assertIn("codex.api_request", serialized)
        self.assertNotIn("codex.run_health", serialized)
        self.assertNotIn("resourceMetrics", serialized)
        self.assertIn("synthetic.scenario", serialized)
        self.assertIn("synthetic.run_id", serialized)
        self.assertIn("stuck-candidate", serialized)

    def test_synthetic_stuck_scenario_has_two_correlated_source_logs(self):
        payload = synthetic_trigger.build_synthetic_payload(
            NOW, "synthetic-stuck-fixture", 660
        )
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
            {"codex.conversation_starts", "codex.api_request"},
        )
        self.assertEqual(
            {item["synthetic.scenario"] for item in attributes}, {"stuck-candidate"}
        )
        self.assertEqual(len({item["synthetic.run_id"] for item in attributes}), 1)
        self.assertEqual(len({item["conversation_id"] for item in attributes}), 1)

    def test_unconfirmed_noncompletion_token_fields_are_not_ingested(self):
        response = {
            "data": {
                "result": [
                    {
                        "stream": {
                            "conversation_id": "synthetic-private-id",
                            "event_name": "codex.sse_event",
                            "input_token_count": "100",
                            "output_token_count": "25",
                        },
                        "values": [["1781784000000000000", ""]],
                    }
                ]
            }
        }
        events, _ = run_health.safe_events_from_loki(response, "fixture-key")
        self.assertNotIn("input_token_count", events[0])
        self.assertNotIn("output_token_count", events[0])
        row = classify(run_health.aggregate_events(events)[0])
        self.assertEqual(row["state"], run_health.SLOW_BUT_ALIVE)
        self.assertNotIn("tokens_observed", row)

    def test_completed_only_summary_is_visibly_healthy_and_private(self):
        run = aggregate(quiet=30)
        run.completed = True
        row = classify(run)
        summary = run_health.format_summary([row], 360)
        self.assertIn("Runs analyzed: 1", summary)
        self.assertIn("Stuck candidates: 0", summary)
        self.assertIn("Healthy outcome:", summary)
        self.assertNotIn("conversation_id", summary)

    def test_summary_contains_only_hashed_run_identifier(self):
        row = classify(aggregate(quiet=900))
        summary = run_health.format_summary([row], 360)
        self.assertIn("run_hash=" + "a" * 64, summary)
        self.assertNotIn("conversation_id", summary)
        for unsafe in ("prompt", "@", "account_id", "cwd=", "arguments=", "output="):
            self.assertNotIn(unsafe, summary)


if __name__ == "__main__":
    unittest.main()
