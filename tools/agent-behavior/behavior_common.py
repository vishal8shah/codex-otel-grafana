#!/usr/bin/env python3
"""Shared privacy-safe helpers for the Codex agent behaviour monitor."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
OBSERVATION_EVENT = "codex.behavior_observation"
OBSERVATION_SERVICE = "Codex Agent Behavior Monitor"
FINDING_EVENT = "codex.behavior_finding"
FINDING_SERVICE = "Codex Agent Behavior Diagnosis"
HEARTBEAT_SIGNAL = "monitor_heartbeat"
ALLOWED_MODES = {"observe", "enforce"}
ALLOWED_SEVERITIES = {"info", "low", "medium", "high", "critical"}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def hmac_identifier(raw: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def finding_identifier(run_hash: str, category: str, first_seen: str, discriminator: str = "") -> str:
    material = f"{run_hash}|{category}|{first_seen}|{discriminator}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


def load_policy(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("policy could not be loaded") from error
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("policy schema version is unsupported")
    if policy.get("default_mode") not in ALLOWED_MODES:
        raise ValueError("policy default mode is invalid")
    if not isinstance(policy.get("rules"), list) or not policy["rules"]:
        raise ValueError("policy rules are missing")
    seen: set[str] = set()
    for rule in policy["rules"]:
        if not isinstance(rule, dict):
            raise ValueError("policy rule is invalid")
        rule_id = str(rule.get("id", ""))
        if not re.fullmatch(r"BEH-\d{3}", rule_id) or rule_id in seen:
            raise ValueError("policy rule id is invalid")
        seen.add(rule_id)
        if rule.get("severity") not in ALLOWED_SEVERITIES or not isinstance(rule.get("enforce"), bool):
            raise ValueError("policy rule attributes are invalid")
    for key in ("protected_resource_patterns", "network_write_patterns", "safe_exceptions"):
        if not isinstance(policy.get(key), list):
            raise ValueError("policy pattern list is missing")
        try:
            [re.compile(str(item), re.IGNORECASE) for item in policy[key]]
        except re.error as error:
            raise ValueError("policy pattern is invalid") from error
    thresholds = policy.get("thresholds")
    if not isinstance(thresholds, dict) or any(not isinstance(value, int) or value < 1 for value in thresholds.values()):
        raise ValueError("policy thresholds are invalid")
    return policy


def policy_rules(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(rule["signal"]): rule for rule in policy["rules"]}


def tool_class(tool_name: str, hook_event: str) -> str:
    normalized = tool_name.strip().lower()
    if hook_event in {"SubagentStart", "SubagentStop"} or normalized in {"agent", "spawn_agent"}:
        return "subagent"
    if normalized == "bash":
        return "shell"
    if normalized in {"apply_patch", "edit", "write"}:
        return "file_edit"
    if normalized.startswith("mcp__"):
        return "mcp"
    if hook_event in {"SessionStart", "SessionEnd", "PreCompact", "PostCompact", "Stop", "Interrupt"}:
        return "lifecycle"
    return "other"


def otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    return {"stringValue": str(value)}


def otlp_logs(service: str, event_name: str, rows: list[dict[str, Any]], at: dt.datetime | None = None) -> dict[str, Any]:
    emitted_at = at or utc_now()
    timestamp_ns = str(int(emitted_at.timestamp() * 1_000_000_000))
    records = []
    for row in rows:
        attributes = {"event_name": event_name, **row}
        records.append(
            {
                "timeUnixNano": timestamp_ns,
                "observedTimeUnixNano": timestamp_ns,
                "severityNumber": 9,
                "severityText": "INFO",
                "body": {"stringValue": ""},
                "attributes": [{"key": key, "value": otlp_value(value)} for key, value in attributes.items()],
            }
        )
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": service}}]},
                "scopeLogs": [{"scope": {"name": event_name, "version": str(SCHEMA_VERSION)}, "logRecords": records}],
            }
        ]
    }


def post_otlp(url: str, payload: dict[str, Any], timeout: int = 10) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.path.endswith("/v1/logs"):
        raise ValueError("OTLP endpoint must be an HTTP(S) /v1/logs URL")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("OTLP emission failed") from error


def safe_serialized(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)
