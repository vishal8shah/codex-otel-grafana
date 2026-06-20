#!/usr/bin/env python3
"""Populate the shipped dashboards with privacy-safe synthetic walkthrough evidence."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_SERVICE_NAME = "Codex Desktop"
PROFILE = "walkthrough-rich"
DERIVED_EVENTS = {
    "codex.run_health",
    "codex.tool_diagnostic",
    "codex.api_diagnostic",
    "codex.slow_contributor",
}
GROUP_FIELDS = {
    "run_health": ("run_hash",),
    "tool_failure": ("run_hash", "tool_name"),
    "api_reliability": ("run_hash", "endpoint_hash"),
    "slow_contributor": ("run_hash", "contributor_type", "endpoint_hash", "tool_name"),
}
ALLOWED_RAW_EVENTS = {
    "codex.conversation_starts",
    "codex.sse_event",
    "codex.api_request",
    "codex.tool_decision",
    "codex.tool_result",
}
UNSAFE_KEYS = {
    "prompt",
    "user_email",
    "user_account_id",
    "api_key",
    "authorization",
    "call_id",
    "cwd",
    "path",
    "arguments",
    "output",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def nanoseconds(value: dt.datetime) -> str:
    return str(int(value.timestamp() * 1_000_000_000))


def otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    return {"stringValue": str(value)}


def log_record(timestamp: dt.datetime, attributes: dict[str, Any]) -> dict[str, Any]:
    event_name = str(attributes.get("event_name", ""))
    if event_name not in ALLOWED_RAW_EVENTS:
        raise ValueError(f"Raw demo event is not schema-confirmed: {event_name}")
    return {
        "timeUnixNano": nanoseconds(timestamp),
        "observedTimeUnixNano": nanoseconds(utc_now()),
        "severityNumber": 9,
        "severityText": "INFO",
        "body": {"stringValue": ""},
        "attributes": [
            {"key": key, "value": otlp_value(value)}
            for key, value in attributes.items()
        ],
    }


def payload(records: list[dict[str, Any]], scope_name: str) -> dict[str, Any]:
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": RAW_SERVICE_NAME},
                        }
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": scope_name, "version": "1"},
                        "logRecords": records,
                    }
                ],
            }
        ]
    }


def trace_payload(now: dt.datetime) -> dict[str, Any]:
    """Build standard synthetic spans for the shipped Tempo/spanmetrics views."""
    span_shapes = (
        ("turn/start", 1, 180),
        ("model_client.stream_responses_websocket", 3, 820),
        ("dispatch_tool_call_with_terminal_outcome", 3, 460),
        ("handle_tool_call", 1, 240),
        ("responses_websocket.stream_request", 3, 1250),
        ("stream_request", 3, 980),
        ("shell_command", 1, 120),
    )
    spans: list[dict[str, Any]] = []
    for index, (name, kind, duration_ms) in enumerate(span_shapes):
        end = now - dt.timedelta(seconds=(len(span_shapes) - index))
        start = end - dt.timedelta(milliseconds=duration_ms)
        spans.append(
            {
                "traceId": uuid.uuid4().hex,
                "spanId": uuid.uuid4().hex[:16],
                "name": name,
                "kind": kind,
                "startTimeUnixNano": nanoseconds(start),
                "endTimeUnixNano": nanoseconds(end),
                "attributes": [
                    {"key": "synthetic", "value": {"boolValue": True}},
                    {"key": "synthetic.demo_profile", "value": {"stringValue": PROFILE}},
                ],
            }
        )
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": RAW_SERVICE_NAME}},
                        {"key": "synthetic", "value": {"boolValue": True}},
                        {"key": "synthetic.demo_profile", "value": {"stringValue": PROFILE}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "codex.synthetic_demo.stack", "version": "1"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }


def validate_trace_payload(body: dict[str, Any]) -> None:
    serialized = json.dumps(body, separators=(",", ":")).lower()
    if "resourcespans" not in serialized or "resourcelogs" in serialized or "resourcemetrics" in serialized:
        raise ValueError("Stack demo payload must contain OTLP traces only.")
    if any(event in serialized for event in DERIVED_EVENTS):
        raise ValueError("Stack demo traces must not contain derived diagnostic records.")
    for key in UNSAFE_KEYS:
        if f'"key":"{key}"' in serialized:
            raise ValueError(f"Stack demo trace payload contains unsafe field: {key}")
    if '"key":"synthetic","value":{"boolvalue":true}' not in serialized:
        raise ValueError("Stack demo traces must be visibly synthetic at the source.")


def shared(source_id: str, env_name: str, scenario: str, run_label: str) -> dict[str, Any]:
    return {
        "conversation_id": source_id,
        "env": env_name,
        "synthetic": True,
        "synthetic.demo_profile": PROFILE,
        "synthetic.scenario": scenario,
        "synthetic.run_id": run_label,
    }


def run_health_scenarios(now: dt.datetime, env_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cases = (
        ("stuck", 900, "codex.api_request", {}),
        ("slow-alive", 60, "codex.api_request", {}),
        ("completed", 180, "codex.sse_event", {"event_kind": "response.completed"}),
        ("unknown-incomplete", 300, "codex.sse_event", {"event_kind": "response.started"}),
    )
    for index, (scenario, quiet_seconds, final_event, extra) in enumerate(cases, start=1):
        source_id = str(uuid.uuid4())
        common = shared(source_id, env_name, scenario, f"run-health-demo-{index}")
        last_seen = now - dt.timedelta(seconds=quiet_seconds)
        records.append(
            log_record(
                last_seen - dt.timedelta(seconds=30),
                {"event_name": "codex.conversation_starts", **common, "model": "synthetic-demo"},
            )
        )
        final_attributes: dict[str, Any] = {"event_name": final_event, **common, **extra}
        if final_event == "codex.api_request":
            final_attributes.update(
                {
                    "duration_ms": 420,
                    "http_response_status_code": 200,
                    "success": True,
                    "endpoint": "/v1/responses/synthetic-demo",
                    "attempt": 1,
                }
            )
        records.append(log_record(last_seen, final_attributes))
    return records


def tool_scenarios(now: dt.datetime, env_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cases = (
        ("failed-result", "synthetic_search", True, False, 780),
        ("selected-no-result", "synthetic_workspace", True, None, None),
        ("successful-result", "synthetic_reader", True, True, 320),
        ("unknown-result", "synthetic_runner", False, None, 510),
    )
    for index, (scenario, tool_name, has_decision, success, duration_ms) in enumerate(cases, start=1):
        common = {
            **shared(str(uuid.uuid4()), env_name, scenario, f"tool-demo-{index}"),
            "tool_name": tool_name,
        }
        stamp = now - dt.timedelta(seconds=100 - index * 10)
        if has_decision:
            records.append(log_record(stamp, {"event_name": "codex.tool_decision", **common}))
        if scenario != "selected-no-result":
            result = {"event_name": "codex.tool_result", **common}
            if success is not None:
                result["success"] = success
            if duration_ms is not None:
                result["duration_ms"] = duration_ms
            records.append(log_record(stamp + dt.timedelta(seconds=4), result))
    return records


def api_scenarios(now: dt.datetime, env_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def add(
        index: int,
        scenario: str,
        events: list[dict[str, Any]],
    ) -> None:
        common = {
            "event_name": "codex.api_request",
            **shared(str(uuid.uuid4()), env_name, scenario, f"api-demo-{index}"),
            "endpoint": f"/v1/responses/synthetic-demo-{index}",
        }
        base = now - dt.timedelta(seconds=100 - index * 10)
        for offset, event in enumerate(events):
            records.append(log_record(base + dt.timedelta(seconds=offset * 3), {**common, **event}))

    add(
        1,
        "failed-request",
        [
            {"duration_ms": 900, "http_response_status_code": 503, "success": False, "attempt": 1},
            {"duration_ms": 700, "http_response_status_code": 200, "success": True, "attempt": 2},
        ],
    )
    add(2, "retried-request", [{"duration_ms": 850, "http_response_status_code": 200, "success": True, "attempt": 2}])
    add(3, "slow-request", [{"duration_ms": 12_800, "http_response_status_code": 200, "success": True, "attempt": 1}])
    add(4, "successful-request", [{"duration_ms": 640, "http_response_status_code": 200, "success": True, "attempt": 1}])
    add(5, "unknown-request", [{"duration_ms": 480}])
    return records


def slow_scenarios(now: dt.datetime, env_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def api(index: int, source_id: str, duration_ms: int) -> None:
        records.append(
            log_record(
                now - dt.timedelta(seconds=90 - index * 10),
                {
                    "event_name": "codex.api_request",
                    **shared(source_id, env_name, "slow-api", f"slow-demo-{index}"),
                    "endpoint": f"/v1/responses/synthetic-slow-{index}",
                    "duration_ms": duration_ms,
                    "http_response_status_code": 200,
                    "success": True,
                    "attempt": 1,
                },
            )
        )

    def tool(index: int, source_id: str, duration_ms: int) -> None:
        records.append(
            log_record(
                now - dt.timedelta(seconds=85 - index * 10),
                {
                    "event_name": "codex.tool_result",
                    **shared(source_id, env_name, "slow-tool", f"slow-demo-{index}"),
                    "tool_name": f"synthetic_slow_tool_{index}",
                    "duration_ms": duration_ms,
                    "success": True,
                },
            )
        )

    api(1, str(uuid.uuid4()), 13_200)
    tool(2, str(uuid.uuid4()), 12_400)
    multiple_source = str(uuid.uuid4())
    api(3, multiple_source, 15_100)
    tool(3, multiple_source, 14_300)
    return records


def build_demo_profile(now: dt.datetime, session: str) -> dict[str, dict[str, Any]]:
    builders = {
        "run_health": run_health_scenarios,
        "tool_failure": tool_scenarios,
        "api_reliability": api_scenarios,
        "slow_contributor": slow_scenarios,
    }
    expected = {
        "run_health": {"COMPLETED_RECENTLY": 1, "SLOW_BUT_ALIVE": 1, "STUCK_CANDIDATE": 1, "UNKNOWN_INCOMPLETE": 1},
        "tool_failure": {"FAILED_RESULT": 1, "SELECTED_NO_RESULT": 1, "SUCCESSFUL_RESULT": 1, "UNKNOWN_RESULT": 1},
        "api_reliability": {"FAILED_REQUEST": 1, "RETRIED_REQUEST": 1, "SLOW_REQUEST": 1, "SUCCESSFUL_REQUEST": 1, "UNKNOWN_REQUEST": 1},
        "slow_contributor": {"SLOW_API_CONTRIBUTOR": 1, "SLOW_TOOL_CONTRIBUTOR": 1, "MULTIPLE_SLOW_CONTRIBUTORS": 2},
    }
    result: dict[str, dict[str, Any]] = {}
    for name, builder in builders.items():
        env_name = f"synthetic-demo-{PROFILE}-{session}-{name.replace('_', '-')}"
        records = builder(now, env_name)
        result[name] = {
            "env": env_name,
            "payload": payload(records, f"codex.synthetic_demo.{name}"),
            "source_records": len(records),
            "expected_states": expected[name],
            "expected_groups": sum(expected[name].values()),
        }
    return result


def validate_demo_profile(profile: dict[str, dict[str, Any]]) -> None:
    serialized = json.dumps(profile, separators=(",", ":")).lower()
    if "resourcemetrics" in serialized or '"metric"' in serialized:
        raise ValueError("Demo scenarios must emit OTLP logs only.")
    if any(event in serialized for event in DERIVED_EVENTS):
        raise ValueError("Demo scenarios must emit raw events, never derived diagnostic records.")
    for key in UNSAFE_KEYS:
        if f'"key":"{key}"' in serialized:
            raise ValueError(f"Demo payload contains unsafe field: {key}")
    if '"key":"synthetic","value":{"boolvalue":true}' not in serialized:
        raise ValueError("Demo payloads must be visibly synthetic at the raw source.")


def post_json(url: str, body: dict[str, Any], endpoint: str = "/v1/logs") -> None:
    parsed = urllib.parse.urlparse(url)
    if endpoint not in {"/v1/logs", "/v1/traces"} or not parsed.path.endswith(endpoint):
        raise ValueError(f"Demo emission is restricted to an OTLP {endpoint} endpoint.")
    request = urllib.request.Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} from OTLP endpoint: {detail[:300]}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach OTLP endpoint: {error.reason}") from error


def analyzer_specs(profile: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "run_health": {
            "script": REPO_ROOT / "tools" / "run-health" / "run_health.py",
            "hash_env": "CODEX_RUN_HEALTH_HASH_KEY",
        },
        "tool_failure": {
            "script": REPO_ROOT / "tools" / "tool-failure" / "tool_failure.py",
            "hash_env": "CODEX_TOOL_DIAG_HASH_KEY",
        },
        "api_reliability": {
            "script": REPO_ROOT / "tools" / "api-reliability" / "api_reliability.py",
            "hash_env": "CODEX_API_DIAG_HASH_KEY",
        },
        "slow_contributor": {
            "script": REPO_ROOT / "tools" / "slow-contributor" / "slow_contributor.py",
            "hash_env": "CODEX_SLOW_CONTRIBUTOR_HASH_KEY",
        },
    }


def state_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(collections.Counter(str(row.get("state", "")) for row in rows))


def privacy_safe_groups(name: str, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    if name not in GROUP_FIELDS:
        raise ValueError(f"Unknown diagnostic group: {name}")
    return [
        {
            **{field: str(row.get(field, "")) for field in GROUP_FIELDS[name]},
            "state": str(row.get("state", "")),
        }
        for row in rows
    ]


def run_analyzer(
    name: str,
    config: dict[str, Any],
    scenario: dict[str, Any],
    args: argparse.Namespace,
    output_path: pathlib.Path,
) -> list[dict[str, Any]]:
    base_command = [
        sys.executable,
        str(config["script"]),
        "--window-minutes",
        str(args.window_minutes),
        "--grafana-url",
        args.grafana_url,
        "--env-filter",
        scenario["env"],
        "--otlp-logs-url",
        args.otlp_logs_url,
        "--output-json",
        str(output_path),
    ]
    environment = os.environ.copy()
    environment[str(config["hash_env"])] = "synthetic-walkthrough-proof-only-hmac-key"
    expected = scenario["expected_states"]
    deadline = time.monotonic() + args.wait_seconds
    rows: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        completed = subprocess.run(
            [*base_command, "--dry-run"],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"{name} analyzer failed: {completed.stderr.strip() or completed.stdout.strip()}")
        rows = json.loads(output_path.read_text(encoding="utf-8"))
        if state_counts(rows) == expected:
            break
        time.sleep(1)
    else:
        raise RuntimeError(
            f"{name} did not reach expected states; expected={expected} observed={state_counts(rows)}"
        )

    completed = subprocess.run(
        [*base_command, "--emit-derived"],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{name} derived emission failed: {completed.stderr.strip() or completed.stdout.strip()}")
    rows = json.loads(output_path.read_text(encoding="utf-8"))
    if state_counts(rows) != expected:
        raise RuntimeError(f"{name} derived rows changed between proof and emission")
    return rows


def parse_window(value: str) -> int:
    normalized = value.strip().lower()
    if normalized.endswith("m"):
        normalized = normalized[:-1]
    try:
        minutes = int(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--window must be minutes, for example 30m") from error
    if minutes < 20 or minutes > 360:
        raise argparse.ArgumentTypeError("--window must be between 20m and 360m")
    return minutes


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populate all shipped diagnostics with a rich synthetic walkthrough profile.")
    parser.add_argument("--profile", default=PROFILE, choices=[PROFILE])
    parser.add_argument("--window", dest="window_minutes", type=parse_window, default=parse_window("30m"))
    parser.add_argument("--otlp-logs-url", default="http://localhost:4318/v1/logs")
    parser.add_argument("--otlp-traces-url", default="http://localhost:4318/v1/traces")
    parser.add_argument("--grafana-url", default="http://localhost:3000")
    parser.add_argument("--wait-seconds", type=int, default=30)
    parser.add_argument("--report-json")
    parser.add_argument("--traces-only", action="store_true", help="Emit only synthetic spans for Tempo/spanmetrics captures.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.wait_seconds < 5:
        print("ERROR: --wait-seconds must be at least 5", file=sys.stderr)
        return 1
    session = uuid.uuid4().hex[:8]
    profile = build_demo_profile(utc_now(), session)
    stack_traces = trace_payload(utc_now())
    try:
        validate_demo_profile(profile)
        validate_trace_payload(stack_traces)
        post_json(args.otlp_traces_url, stack_traces, "/v1/traces")

        if args.traces_only:
            report = {
                "profile": args.profile,
                "proof_path": "synthetic OTLP traces -> Tempo -> generated spanmetrics -> Grafana",
                "synthetic_trace_spans_emitted": len(stack_traces["resourceSpans"][0]["scopeSpans"][0]["spans"]),
            }
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        for scenario in profile.values():
            post_json(args.otlp_logs_url, scenario["payload"])

        report = {
            "profile": args.profile,
            "window_minutes": args.window_minutes,
            "proof_path": "synthetic OTLP -> Loki raw evidence -> shipped analyzers -> Loki derived records -> Grafana",
            "synthetic_trace_spans_emitted": len(stack_traces["resourceSpans"][0]["scopeSpans"][0]["spans"]),
            "diagnostics": {},
        }
        specs = analyzer_specs(profile)
        with tempfile.TemporaryDirectory(prefix="codex-demo-") as temp_dir:
            for name, scenario in profile.items():
                rows = run_analyzer(
                    name,
                    specs[name],
                    scenario,
                    args,
                    pathlib.Path(temp_dir) / f"{name}.json",
                )
                report["diagnostics"][name] = {
                    "source_records_emitted": scenario["source_records"],
                    "unique_groups_expected": scenario["expected_groups"],
                    "derived_groups_emitted": len(rows),
                    "states": state_counts(rows),
                    "privacy_safe_groups": privacy_safe_groups(name, rows),
                }

        if args.report_json:
            report_path = pathlib.Path(args.report_json).expanduser()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
