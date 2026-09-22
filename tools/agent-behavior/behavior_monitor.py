#!/usr/bin/env python3
"""Normalize one Codex hook event into a privacy-safe behaviour observation."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from behavior_common import (
    HEARTBEAT_SIGNAL,
    OBSERVATION_EVENT,
    OBSERVATION_SERVICE,
    SCHEMA_VERSION,
    hmac_identifier,
    iso_utc,
    load_policy,
    otlp_logs,
    policy_rules,
    post_otlp,
    safe_serialized,
    tool_class,
    utc_now,
)


SUPPORTED_HOOKS = {
    "SessionStart", "SessionEnd", "PreToolUse", "PostToolUse", "PermissionRequest",
    "SubagentStart", "SubagentStop", "PreCompact", "PostCompact", "Stop", "Interrupt",
}
UNSAFE_ATTRIBUTE_NAMES = {
    "prompt", "command", "arguments", "output", "tool_input", "tool_response", "path",
    "cwd", "session_id", "turn_id", "tool_use_id", "transcript_path", "agent_id", "domain",
    "credential", "secret", "token", "authorization",
}
PERMISSION_MODES = {
    "accept_edits", "bypass_permissions", "default", "full_access", "never", "plan",
    "read_only", "workspace_write",
}


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def first_match(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def classify_signal(event: dict[str, Any], policy: dict[str, Any]) -> str:
    hook_event = str(event.get("hook_event_name", ""))
    name = str(event.get("tool_name", ""))
    raw = flatten_text(event.get("tool_input"))
    lowered = raw.lower()
    network_write = first_match(lowered, policy["network_write_patterns"]) and not first_match(
        lowered, policy["safe_exceptions"]
    )

    if hook_event in {"SubagentStart", "SubagentStop"} or name.lower() in {"agent", "spawn_agent"}:
        return "subagent_activity"
    if hook_event == "PermissionRequest":
        return "permission_request"
    if hook_event == "SessionStart":
        return HEARTBEAT_SIGNAL
    if hook_event not in {"PreToolUse", "PostToolUse"}:
        return "lifecycle_activity"
    if first_match(lowered, policy["protected_resource_patterns"]):
        if network_write:
            return "credential_outbound_use"
        return "sensitive_resource_probe"
    if re.search(r"(?:dangerously-bypass|--yolo|disable.{0,20}(?:sandbox|hook|otel|logging)|remove-item.{0,20}hooks\.json)", lowered):
        return "control_bypass_attempt"
    if re.search(r"(?:\brm\s+-rf\b|remove-item\b.{0,80}-recurse|\bdel\s+/[sq]\b|format(?:-volume)?\b)", lowered):
        return "destructive_filesystem_action"
    if re.search(r"(?:schtasks|register-scheduledtask|crontab|systemctl\s+enable|launchctl|startup)", lowered):
        return "persistence_creation"
    if network_write:
        if re.search(r"(?:git\s+push|release\s+create|pr\s+create|publish|hf\s+upload)", lowered):
            return "public_mutation"
        return "external_write"
    if re.search(r"(?:/etc/|/root/|/proc/|/sys/|\\windows\\system32|\\users\\[^\\]+\\\.codex)", lowered):
        return "workspace_boundary_attempt"
    if re.search(r"(?:\benv\b|printenv|set\s*$|mountinfo|/proc/(?:self|1)|ifconfig|ipconfig|netstat|route\s+print|whoami|id\s*$)", lowered):
        return "environment_reconnaissance"
    return "tool_activity"


def result_action(event: dict[str, Any], signal: str, mode: str, rule: dict[str, Any]) -> str:
    hook_event = str(event.get("hook_event_name", ""))
    if hook_event == "PermissionRequest":
        return "observed"
    if hook_event == "PostToolUse":
        response = event.get("tool_response")
        if isinstance(response, dict) and (response.get("isError") is True or response.get("success") is False):
            return "failed"
        return "completed"
    if hook_event == "PreToolUse" and mode == "enforce" and rule.get("enforce") is True and rule.get("severity") in {"high", "critical"}:
        return "denied"
    if hook_event == "PreToolUse":
        return "allowed" if signal == "tool_activity" else "observed"
    return "observed"


def normalize(event: dict[str, Any], policy: dict[str, Any], mode: str, hash_key: str, synthetic: bool) -> dict[str, Any]:
    hook_event = str(event.get("hook_event_name", ""))
    if hook_event not in SUPPORTED_HOOKS:
        raise ValueError("hook event is unsupported")
    session_id = str(event.get("session_id", ""))
    if not session_id:
        raise ValueError("hook event is missing a session identifier")
    signal = classify_signal(event, policy)
    rule = policy_rules(policy).get(signal)
    if rule is None:
        raise ValueError("policy does not define the classified signal")
    turn_id = str(event.get("turn_id", ""))
    action = result_action(event, signal, mode, rule)
    permission_mode = re.sub(r"(?<!^)(?=[A-Z])", "_", str(event.get("permission_mode", "unknown"))).lower()
    if permission_mode not in PERMISSION_MODES:
        permission_mode = "unknown"
    observation = {
        "schema_version": SCHEMA_VERSION,
        "run_hash": hmac_identifier(session_id, hash_key),
        "turn_hash": hmac_identifier(turn_id, hash_key) if turn_id else "",
        "hook_event": hook_event,
        "tool_class": tool_class(str(event.get("tool_name", "")), hook_event),
        "behavior_signal": signal,
        "policy_rule_id": str(rule["id"]),
        "severity": str(rule["severity"]),
        "policy_mode": mode,
        "policy_action": action,
        "permission_mode": permission_mode,
        "synthetic": synthetic,
        "evidence_source": "synthetic_hook_fixture" if synthetic else "codex_hook",
        "observed_at": iso_utc(utc_now()),
        "signal_count": 1,
    }
    if signal == HEARTBEAT_SIGNAL:
        observation["severity"] = "info"
    return observation


def hook_response(observation: dict[str, Any]) -> dict[str, Any]:
    if observation["policy_action"] != "denied":
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Blocked by local behaviour policy {observation['policy_rule_id']}.",
        }
    }


def assert_safe(payload: dict[str, Any]) -> None:
    for resource in payload.get("resourceLogs", []):
        for scope in resource.get("scopeLogs", []):
            for record in scope.get("logRecords", []):
                if record.get("body", {}).get("stringValue"):
                    raise ValueError("observation body must be empty")
                keys = {str(item.get("key", "")).lower() for item in record.get("attributes", [])}
                if keys.intersection(UNSAFE_ATTRIBUTE_NAMES):
                    raise ValueError("observation contains an unsafe attribute")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize one Codex hook event into privacy-safe OTLP evidence.")
    parser.add_argument("--policy", default=str(Path(__file__).with_name("policy.json")))
    parser.add_argument("--mode", choices=("observe", "enforce"))
    parser.add_argument("--hash-key-file")
    parser.add_argument("--otlp-logs-url", default=os.environ.get("CODEX_BEHAVIOR_OTLP_URL", "http://localhost:4318/v1/logs"))
    parser.add_argument("--input-json", help="Read a hook fixture from a file instead of stdin.")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-observation", action="store_true")
    return parser.parse_args(argv)


def read_hash_key(args: argparse.Namespace, event: dict[str, Any]) -> str:
    environment_key = os.environ.get("CODEX_BEHAVIOR_HASH_KEY")
    if environment_key:
        return environment_key
    candidate = Path(args.hash_key_file) if args.hash_key_file else Path(str(event.get("cwd", "."))) / ".codex" / "behavior-monitor.key"
    try:
        key = candidate.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ValueError("behaviour hash key is unavailable") from error
    if len(key) < 32:
        raise ValueError("behaviour hash key is invalid")
    return key


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mode_for_failure = args.mode or os.environ.get("CODEX_BEHAVIOR_MODE") or "observe"
    try:
        policy = load_policy(Path(args.policy))
        mode = args.mode or os.environ.get("CODEX_BEHAVIOR_MODE") or str(policy["default_mode"])
        if mode not in {"observe", "enforce"}:
            raise ValueError("behaviour mode is invalid")
        if args.input_json:
            event = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        else:
            event = json.load(sys.stdin)
        hash_key = read_hash_key(args, event)
        observation = normalize(event, policy, mode, hash_key, args.synthetic)
        payload = otlp_logs(OBSERVATION_SERVICE, OBSERVATION_EVENT, [observation])
        assert_safe(payload)
        if not args.dry_run:
            post_otlp(args.otlp_logs_url, payload)
        if args.print_observation:
            print(safe_serialized(observation), file=sys.stderr)
        response = hook_response(observation)
        if response:
            print(json.dumps(response, separators=(",", ":")))
        return 0
    except (ValueError, RuntimeError, json.JSONDecodeError, OSError):
        print("Codex behaviour monitor failed safely; raw hook data was not retained.", file=sys.stderr)
        if mode_for_failure == "enforce":
            print(json.dumps({"decision": "block", "reason": "Behaviour policy could not be evaluated safely."}, separators=(",", ":")))
            return 2
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
