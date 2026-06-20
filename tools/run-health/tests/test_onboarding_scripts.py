import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


REPO_ROOT = pathlib.Path(__file__).parents[3]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


preflight = load_script("onboarding_preflight", "preflight.py")
health = load_script("onboarding_health", "health-check.py")
proof = load_script("onboarding_proof", "run-onboarding-demo.py")


class PreflightTests(unittest.TestCase):
    @mock.patch.object(preflight, "port_open", return_value=False)
    @mock.patch.object(preflight, "run")
    @mock.patch.object(preflight.shutil, "which", return_value="docker")
    def test_preflight_checks_local_prerequisites_without_installing(self, _which, run, _port):
        run.side_effect = [
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="Docker Compose version v2", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
        ]
        checks = preflight.collect_checks()
        self.assertTrue(all(check.ok for check in checks))
        self.assertTrue(any(check.name == "Secrets" and "none required" in check.detail for check in checks))


class HealthCheckTests(unittest.TestCase):
    def test_rejects_non_local_grafana_url(self):
        with self.assertRaises(Exception):
            health.local_url("https://example.com")
        self.assertEqual(health.local_url("http://127.0.0.1:3000"), "http://127.0.0.1:3000")


class OnboardingProofTests(unittest.TestCase):
    def test_command_center_states_are_loaded_from_shipped_dashboard(self):
        states = proof.command_center_issue_states()
        self.assertEqual(set(states), set(proof.CONTRACTS))
        self.assertIn("STUCK_CANDIDATE", states["run_health"])
        self.assertNotIn("COMPLETED_RECENTLY", states["run_health"])

    def test_expected_groups_use_profile_keys_not_literal_counts(self):
        contract = proof.CONTRACTS["tool_failure"]
        report = {
            "diagnostics": {
                "tool_failure": {
                    "unique_groups_expected": 2,
                    "privacy_safe_groups": [
                        {"run_hash": "a", "tool_name": "one", "state": "FAILED_RESULT"},
                        {"run_hash": "b", "tool_name": "two", "state": "SUCCESSFUL_RESULT"},
                    ],
                }
            }
        }
        self.assertEqual(
            proof.expected_groups(report, "tool_failure", contract),
            {("a", "one"): "FAILED_RESULT", ("b", "two"): "SUCCESSFUL_RESULT"},
        )

    @mock.patch.object(proof, "get_json")
    def test_loki_results_are_deduplicated_by_shipped_grouping_grain(self, get_json):
        get_json.return_value = {
            "data": {
                "result": [
                    {"stream": {"run_hash": "a", "tool_name": "reader", "state": "FAILED_RESULT"}},
                    {"stream": {"run_hash": "a", "tool_name": "reader", "state": "FAILED_RESULT"}},
                ]
            }
        }
        observed = proof.query_groups(
            "http://localhost:3000",
            proof.CONTRACTS["tool_failure"],
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "admin",
            "admin",
        )
        self.assertEqual(observed, {("a", "reader"): {"FAILED_RESULT"}})


if __name__ == "__main__":
    unittest.main()
