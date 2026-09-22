#!/usr/bin/env python3
"""Validate Phase 8 privacy, policy, dashboard, and demo contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BEHAVIOR = ROOT / "tools" / "agent-behavior"
sys.path.insert(0, str(BEHAVIOR))

from behavior_common import OBSERVATION_EVENT, OBSERVATION_SERVICE, load_policy, otlp_logs  # noqa: E402
from behavior_demo import build_observations  # noqa: E402
from behavior_hooks import EVENTS  # noqa: E402
from behavior_monitor import SUPPORTED_HOOKS, UNSAFE_ATTRIBUTE_NAMES, assert_safe  # noqa: E402


EXPECTED_HOOKS = {
    "SessionStart", "SessionEnd", "PreToolUse", "PostToolUse", "PermissionRequest",
    "SubagentStart", "SubagentStop", "PreCompact", "PostCompact", "Stop", "Interrupt",
}
SAFE_OBSERVATION_KEYS = {
    "schema_version", "run_hash", "turn_hash", "hook_event", "tool_class", "behavior_signal",
    "policy_rule_id", "severity", "policy_mode", "policy_action", "permission_mode", "synthetic",
    "evidence_source", "observed_at", "signal_count", "timestamp",
}
FORBIDDEN_QUERY_TERMS = {
    "prompt", "command", "arguments", "tool_input", "tool_response", "output", "path", "cwd",
    "session_id", "turn_id", "tool_use_id", "transcript", "agent_id", "domain", "credential",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    policy = load_policy(BEHAVIOR / "policy.json")
    if SUPPORTED_HOOKS != EXPECTED_HOOKS or set(EVENTS) != EXPECTED_HOOKS:
        fail("Hook coverage differs between the monitor, installer, and Phase 8 contract")
    if "UserPromptSubmit" in SUPPORTED_HOOKS or "UserPromptSubmit" in EVENTS:
        fail("UserPromptSubmit must never be registered")

    observations = build_observations(policy)
    for row in observations:
        unexpected = set(row) - SAFE_OBSERVATION_KEYS
        if unexpected:
            fail(f"Observation contains unapproved keys: {sorted(unexpected)}")
        if set(key.lower() for key in row).intersection(UNSAFE_ATTRIBUTE_NAMES):
            fail("Observation contains an unsafe attribute name")
    wire_rows = [{key: value for key, value in row.items() if key != "timestamp"} for row in observations]
    payload = otlp_logs(OBSERVATION_SERVICE, OBSERVATION_EVENT, wire_rows)
    assert_safe(payload)
    serialized = json.dumps(payload, separators=(",", ":")).lower()
    for raw_fragment in ("echo safe-demo", "printenv", "synthetic-target", "example.invalid", "git push"):
        if raw_fragment in serialized:
            fail("Raw synthetic hook input reached the OTLP payload")

    dashboard_path = ROOT / "observability" / "dashboards" / "codex-agent-behavior-security.json"
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    if dashboard.get("uid") != "codex-agent-behavior-security":
        fail("Behaviour dashboard UID is invalid")
    queries = " ".join(
        str(target.get("expr", ""))
        for panel in dashboard.get("panels", [])
        for target in panel.get("targets", [])
    ).lower()
    bad_terms = sorted(term for term in FORBIDDEN_QUERY_TERMS if term in queries)
    if bad_terms:
        fail(f"Behaviour dashboard queries unsafe fields: {bad_terms}")
    if "codex.behavior_finding" not in queries or "codex.behavior_observation" not in queries:
        fail("Behaviour dashboard does not cover both safe event streams")

    alert_text = (ROOT / "observability" / "provisioning" / "alerting" / "behavior-notification.yaml").read_text(encoding="utf-8")
    if 'severity=~\\"high|critical\\"' not in alert_text or "codex.behavior_finding" not in alert_text:
        fail("Behaviour alert does not target fresh high/critical findings")

    print(f"Validated {len(observations)} safe demo observations, {len(EXPECTED_HOOKS)} hook events, dashboard, and alert contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
