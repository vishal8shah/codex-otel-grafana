import datetime as dt
import importlib.util
import pathlib
import sys
import unittest


SCRIPT_PATH = pathlib.Path(__file__).parents[3] / "scripts" / "emit-demo-scenarios.py"
SPEC = importlib.util.spec_from_file_location("emit_demo_scenarios", SCRIPT_PATH)
demo = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = demo
SPEC.loader.exec_module(demo)


class DemoScenarioTests(unittest.TestCase):
    def setUp(self):
        self.profile = demo.build_demo_profile(
            dt.datetime(2026, 6, 20, 3, 0, tzinfo=dt.timezone.utc),
            "fixture",
        )

    def test_profile_covers_all_shipped_diagnostics(self):
        self.assertEqual(
            set(self.profile),
            {"run_health", "tool_failure", "api_reliability", "slow_contributor"},
        )
        self.assertEqual(self.profile["run_health"]["expected_groups"], 4)
        self.assertEqual(self.profile["tool_failure"]["expected_groups"], 4)
        self.assertEqual(self.profile["api_reliability"]["expected_groups"], 5)
        self.assertEqual(self.profile["slow_contributor"]["expected_groups"], 4)

    def test_profile_emits_raw_logs_only(self):
        demo.validate_demo_profile(self.profile)
        serialized = str(self.profile).lower()
        self.assertNotIn("resourcemetrics", serialized)
        for event_name in demo.DERIVED_EVENTS:
            self.assertNotIn(event_name, serialized)

    def test_expected_state_variety_is_explicit(self):
        self.assertEqual(
            set(self.profile["run_health"]["expected_states"]),
            {"COMPLETED_RECENTLY", "SLOW_BUT_ALIVE", "STUCK_CANDIDATE", "UNKNOWN_INCOMPLETE"},
        )
        self.assertEqual(
            set(self.profile["tool_failure"]["expected_states"]),
            {"FAILED_RESULT", "SELECTED_NO_RESULT", "SUCCESSFUL_RESULT", "UNKNOWN_RESULT"},
        )
        self.assertEqual(
            set(self.profile["api_reliability"]["expected_states"]),
            {"FAILED_REQUEST", "RETRIED_REQUEST", "SLOW_REQUEST", "SUCCESSFUL_REQUEST", "UNKNOWN_REQUEST"},
        )

    def test_payload_has_no_unsafe_optional_fields(self):
        serialized = str(self.profile).lower()
        for key in demo.UNSAFE_KEYS:
            self.assertNotIn(f"'key': '{key}'", serialized)

    def test_stack_trace_payload_is_synthetic_and_safe(self):
        body = demo.trace_payload(dt.datetime(2026, 6, 20, 3, 0, tzinfo=dt.timezone.utc))
        demo.validate_trace_payload(body)
        spans = body["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(len(spans), 7)
        resource_attributes = body["resourceSpans"][0]["resource"]["attributes"]
        self.assertIn(
            {"key": "service.name", "value": {"stringValue": demo.RAW_SERVICE_NAME}},
            resource_attributes,
        )
        self.assertEqual(
            {span["name"] for span in spans},
            {
                "turn/start",
                "model_client.stream_responses_websocket",
                "dispatch_tool_call_with_terminal_outcome",
                "handle_tool_call",
                "responses_websocket.stream_request",
                "stream_request",
                "shell_command",
            },
        )
        serialized = str(body).lower()
        self.assertNotIn("resourcemetrics", serialized)
        for key in demo.UNSAFE_KEYS:
            self.assertNotIn(f"'key': '{key}'", serialized)


if __name__ == "__main__":
    unittest.main()
