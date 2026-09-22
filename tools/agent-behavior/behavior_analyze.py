#!/usr/bin/env python3
"""Correlate privacy-safe behaviour observations into bounded findings."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from behavior_common import (
    FINDING_EVENT,
    FINDING_SERVICE,
    OBSERVATION_EVENT,
    OBSERVATION_SERVICE,
    finding_identifier,
    iso_utc,
    load_policy,
    otlp_logs,
    parse_iso,
    post_otlp,
    utc_now,
)


SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
STATE_ORDER = {"OBSERVED": 0, "COMPLETED": 1, "INCOMPLETE": 2, "BLOCKED": 3}
EXPLANATIONS = {
    "high_risk_action": "A deterministic high-risk tool-policy signal was observed.",
    "recon_to_sensitive_probe": "Reconnaissance was followed by a sensitive-resource probe in the selected window.",
    "credential_to_egress": "Sensitive-resource activity was followed by an external write signal.",
    "repeated_denial": "The same run produced repeated denied policy actions.",
    "destructive_sequence": "Workspace-boundary activity was followed by a destructive filesystem signal.",
    "subagent_high_risk_sequence": "Subagent activity and a high-risk tool signal occurred in one run.",
    "persistence_network_sequence": "Persistence creation and external network-write signals occurred in one run.",
    "multi_category_escalation": "Multiple distinct risk categories occurred in one run.",
    "subagent_burst": "Subagent activity exceeded the configured local investigation threshold.",
    "unusual_tool_volume": "Tool activity exceeded the configured local investigation threshold.",
    "repeated_failure": "Repeated failed tool outcomes were observed in one run.",
}
NEXT_ACTIONS = {
    "BLOCKED": "Review the policy rule and surrounding privacy-safe evidence before allowing a retry.",
    "INCOMPLETE": "Inspect the supported tool path and local runtime before repeating the action.",
    "COMPLETED": "Confirm the completed action was authorized and within the intended workspace boundary.",
    "OBSERVED": "Review the correlated signals and confirm they match the intended task and permissions.",
}


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def grafana_headers() -> dict[str, str]:
    user = os.environ.get("GRAFANA_USER", "admin")
    password = os.environ.get("GRAFANA_PASSWORD", "admin")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=grafana_headers())
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("local Grafana query failed") from error


def query_loki(grafana_url: str, window_minutes: int, limit: int, now: dt.datetime) -> dict[str, Any]:
    query = f'{{service_name={json.dumps(OBSERVATION_SERVICE)}}} | event_name={json.dumps(OBSERVATION_EVENT)}'
    params = urllib.parse.urlencode(
        {
            "query": query,
            "start": str(int((now - dt.timedelta(minutes=window_minutes)).timestamp() * 1_000_000_000)),
            "end": str(int(now.timestamp() * 1_000_000_000)),
            "limit": str(limit),
            "direction": "forward",
        }
    )
    return get_json(f"{grafana_url.rstrip('/')}/api/datasources/proxy/uid/loki/loki/api/v1/query_range?{params}")


def observations_from_loki(response: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    values_seen = 0
    allowed = {
        "run_hash", "turn_hash", "hook_event", "tool_class", "behavior_signal", "policy_rule_id",
        "severity", "policy_mode", "policy_action", "permission_mode", "synthetic", "evidence_source",
        "observed_at", "signal_count",
    }
    for stream in response.get("data", {}).get("result", []):
        labels = stream.get("stream", {})
        if not isinstance(labels, dict):
            continue
        safe = {key: labels.get(key, "") for key in allowed}
        if not safe["run_hash"] or not safe["behavior_signal"]:
            continue
        for value in stream.get("values", []):
            values_seen += 1
            timestamp = dt.datetime.fromtimestamp(int(value[0]) / 1_000_000_000, tz=dt.timezone.utc)
            row = dict(safe)
            if row.get("observed_at"):
                try:
                    timestamp = parse_iso(str(row["observed_at"]))
                except ValueError:
                    pass
            row["timestamp"] = timestamp
            row["synthetic"] = parse_bool(row["synthetic"])
            rows.append(row)
    return rows, values_seen


def observation_state(rows: Iterable[dict[str, Any]]) -> str:
    states = []
    for row in rows:
        action = row.get("policy_action")
        states.append({"denied": "BLOCKED", "failed": "INCOMPLETE", "completed": "COMPLETED"}.get(action, "OBSERVED"))
    return max(states or ["OBSERVED"], key=STATE_ORDER.__getitem__)


def max_severity(rows: Iterable[dict[str, Any]], floor: str = "info") -> str:
    values = [str(row.get("severity", "info")) for row in rows]
    values.append(floor)
    return max(values, key=lambda item: SEVERITY_ORDER.get(item, 0))


def make_finding(run_hash: str, category: str, rows: list[dict[str, Any]], severity: str | None = None) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row["timestamp"])
    first_seen = iso_utc(ordered[0]["timestamp"])
    last_seen = iso_utc(ordered[-1]["timestamp"])
    state = observation_state(ordered)
    sources = {str(row.get("evidence_source", "unknown")) for row in ordered}
    rule_ids = ",".join(sorted({str(row.get("policy_rule_id", "")) for row in ordered if row.get("policy_rule_id")}))
    return {
        "run_hash": run_hash,
        "finding_id": finding_identifier(run_hash, category, first_seen, rule_ids),
        "category": category,
        "severity": severity or max_severity(ordered),
        "state": state,
        "rule_ids": rule_ids,
        "signal_count": len(ordered),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "evidence_source": next(iter(sources)) if len(sources) == 1 else "mixed_safe_evidence",
        "grouping_precision": "privacy_safe_run_window",
        "explanation": EXPLANATIONS[category],
        "next_action": NEXT_ACTIONS[state],
        "synthetic": all(bool(row.get("synthetic")) for row in ordered),
        "source": "derived",
    }


def correlate(observations: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        grouped[str(row["run_hash"])].append(row)
    findings: list[dict[str, Any]] = []
    thresholds = policy["thresholds"]
    for run_hash, rows in grouped.items():
        rows.sort(key=lambda row: row["timestamp"])
        by_signal: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_signal[str(row["behavior_signal"])].append(row)

        for signal in (
            "sensitive_resource_probe", "destructive_filesystem_action", "control_bypass_attempt",
            "external_write", "public_mutation", "persistence_creation", "workspace_boundary_attempt",
            "credential_outbound_use",
        ):
            if by_signal[signal]:
                findings.append(make_finding(run_hash, "high_risk_action", by_signal[signal]))

        sequence_specs = (
            ("recon_to_sensitive_probe", "environment_reconnaissance", "sensitive_resource_probe", "high"),
            ("credential_to_egress", "sensitive_resource_probe", "external_write", "critical"),
            ("credential_to_egress", "sensitive_resource_probe", "public_mutation", "critical"),
            ("destructive_sequence", "workspace_boundary_attempt", "destructive_filesystem_action", "critical"),
            ("subagent_high_risk_sequence", "subagent_activity", "destructive_filesystem_action", "critical"),
            ("subagent_high_risk_sequence", "subagent_activity", "credential_outbound_use", "critical"),
            ("persistence_network_sequence", "persistence_creation", "external_write", "critical"),
        )
        emitted_categories: set[str] = set()
        for category, before, after, severity in sequence_specs:
            if category in emitted_categories or not by_signal[before] or not by_signal[after]:
                continue
            if category == "subagent_high_risk_sequence" and len(by_signal[before]) < thresholds["subagent_burst"]:
                continue
            pairs = [
                (left, right)
                for left in by_signal[before]
                for right in by_signal[after]
                if dt.timedelta(0) <= right["timestamp"] - left["timestamp"] <= dt.timedelta(seconds=thresholds["correlation_window_seconds"])
            ]
            if pairs:
                left, right = min(pairs, key=lambda pair: pair[1]["timestamp"])
                matched = by_signal[before] + [right] if category == "subagent_high_risk_sequence" else [left, right]
                findings.append(make_finding(run_hash, category, matched, severity))
                emitted_categories.add(category)

        denied = [row for row in rows if row.get("policy_action") == "denied"]
        if len(denied) >= thresholds["repeated_denial"]:
            findings.append(make_finding(run_hash, "repeated_denial", denied, "critical"))
        subagents = by_signal["subagent_activity"]
        if len(subagents) >= thresholds["subagent_burst"]:
            findings.append(make_finding(run_hash, "subagent_burst", subagents, "medium"))
        tool_rows = [row for row in rows if row.get("tool_class") in {"shell", "file_edit", "mcp", "other"}]
        if len(tool_rows) >= thresholds["unusual_tool_volume"]:
            findings.append(make_finding(run_hash, "unusual_tool_volume", tool_rows, "medium"))
        failures = [row for row in rows if row.get("policy_action") == "failed"]
        if len(failures) >= thresholds["repeated_failure"]:
            findings.append(make_finding(run_hash, "repeated_failure", failures, "medium"))
        risky_categories = {row["behavior_signal"] for row in rows if SEVERITY_ORDER.get(str(row.get("severity")), 0) >= 2}
        if len(risky_categories) >= 3:
            findings.append(make_finding(run_hash, "multi_category_escalation", rows, "critical"))

    unique = {(row["run_hash"], row["category"], row["finding_id"]): row for row in findings}
    return sorted(unique.values(), key=lambda row: (SEVERITY_ORDER[row["severity"]], row["last_seen"]), reverse=True)


def parse_fixture(path: str) -> list[dict[str, Any]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("observation fixture must be a JSON array")
    for row in rows:
        row["timestamp"] = parse_iso(str(row.pop("timestamp")))
    return rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Correlate privacy-safe Codex behaviour observations.")
    parser.add_argument("--window-minutes", type=int, default=360)
    parser.add_argument("--grafana-url", default="http://localhost:3000")
    parser.add_argument("--policy", default=str(Path(__file__).with_name("policy.json")))
    parser.add_argument("--loki-limit", type=int, default=5000)
    parser.add_argument("--observations-json")
    parser.add_argument("--output-json")
    parser.add_argument("--emit-derived", action="store_true")
    parser.add_argument("--otlp-logs-url", default="http://localhost:4318/v1/logs")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.window_minutes < 1 or args.loki_limit < 1 or (args.dry_run and args.emit_derived):
            raise ValueError("analyzer arguments are invalid")
        policy = load_policy(Path(args.policy))
        if args.observations_json:
            observations = parse_fixture(args.observations_json)
            value_count = len(observations)
        else:
            observations, value_count = observations_from_loki(query_loki(args.grafana_url, args.window_minutes, args.loki_limit, utc_now()))
        findings = correlate(observations, policy)
        if args.output_json:
            Path(args.output_json).write_text(json.dumps(findings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.emit_derived and findings:
            post_otlp(args.otlp_logs_url, otlp_logs(FINDING_SERVICE, FINDING_EVENT, findings))
        if value_count >= args.loki_limit:
            print("WARNING: observation query reached the configured limit; findings may be incomplete.", file=sys.stderr)
        counts: dict[str, int] = defaultdict(int)
        for row in findings:
            counts[row["severity"]] += 1
        print(f"Codex Agent Behaviour Security: observations={value_count} findings={len(findings)} high={counts['high']} critical={counts['critical']}")
        return 0
    except (ValueError, RuntimeError, json.JSONDecodeError, OSError):
        print("ERROR: behaviour analysis failed without retaining raw hook data.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
