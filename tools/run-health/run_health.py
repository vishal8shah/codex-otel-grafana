#!/usr/bin/env python3
"""Privacy-safe stuck-run triage derived from observed Codex Loki fields."""

from __future__ import annotations

import argparse
import base64
import dataclasses
import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from typing import Any


COMPLETED_RECENTLY = "COMPLETED_RECENTLY"
SLOW_BUT_ALIVE = "SLOW_BUT_ALIVE"
STUCK_CANDIDATE = "STUCK_CANDIDATE"
UNKNOWN_INCOMPLETE = "UNKNOWN_INCOMPLETE"

DERIVED_EVENT_NAME = "codex.run_health"
DERIVED_SERVICE_NAME = "Codex Run Health"
DEFAULT_SERVICE_NAME = "Codex Desktop"

# These names are an explicit no-emission guard. This tool emits OTLP logs only.
FORBIDDEN_NATIVE_METRICS = (
    "codex.api_request",
    "codex.api_request.duration_ms",
    "codex.sse_event",
    "codex.sse_event.duration_ms",
    "codex.websocket.request",
    "codex.websocket.request.duration_ms",
    "codex.websocket.event",
    "codex.websocket.event.duration_ms",
    "codex.tool.call",
    "codex.tool.call.duration_ms",
)

MEANINGFUL_EVENTS = {
    "codex.conversation_starts",
    "codex.user_prompt",
    "codex.api_request",
    "codex.sse_event",
    "codex.turn_ttft",
    "codex.websocket_connect",
    "codex.websocket_event",
    "codex.websocket_request",
    "codex.tool_decision",
    "codex.tool_result",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_loki_timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(value) / 1_000_000_000, tz=dt.timezone.utc)


def hash_run_identifier(raw_identifier: str, key: str | None) -> str:
    encoded = raw_identifier.encode("utf-8")
    if key:
        return hmac.new(key.encode("utf-8"), encoded, hashlib.sha256).hexdigest()
    return hashlib.sha256(encoded).hexdigest()


@dataclasses.dataclass
class RunAggregate:
    run_hash: str
    first_seen: dt.datetime
    last_seen: dt.datetime
    last_event: str = "unknown"
    model: str = "unknown"
    event_count: int = 0
    completed: bool = False
    meaningful_activity: bool = False

    def add_event(self, event: dict[str, Any]) -> None:
        timestamp = event["timestamp"]
        self.first_seen = min(self.first_seen, timestamp)
        if timestamp >= self.last_seen:
            self.last_seen = timestamp
            self.last_event = event["event_name"]
            if event.get("model"):
                self.model = event["model"]
        self.event_count += 1
        self.meaningful_activity = self.meaningful_activity or event["event_name"] in MEANINGFUL_EVENTS
        self.completed = self.completed or (
            event["event_name"] == "codex.sse_event"
            and event.get("event_kind") == "response.completed"
        )


def classify_run(
    run: RunAggregate,
    now: dt.datetime,
    alive_threshold_seconds: int,
    stuck_threshold_seconds: int,
    analysis_window_minutes: int,
) -> dict[str, Any]:
    age_seconds = max(0, int((now - run.first_seen).total_seconds()))
    quiet_for_seconds = max(0, int((now - run.last_seen).total_seconds()))

    if run.completed:
        state = COMPLETED_RECENTLY
        notes = "Completion observed in the analysis window."
    elif quiet_for_seconds <= alive_threshold_seconds:
        state = SLOW_BUT_ALIVE
        notes = "Recent schema-confirmed activity observed; completion not yet seen."
    elif run.meaningful_activity and quiet_for_seconds >= stuck_threshold_seconds:
        state = STUCK_CANDIDATE
        notes = "Meaningful activity went quiet beyond the threshold; candidate only."
    else:
        state = UNKNOWN_INCOMPLETE
        notes = "Insufficient confirmed evidence for alive or stuck classification."

    return {
        "run_hash": run.run_hash,
        "state": state,
        "first_seen": iso_utc(run.first_seen),
        "last_seen": iso_utc(run.last_seen),
        "age_seconds": age_seconds,
        "quiet_for_seconds": quiet_for_seconds,
        "completed": run.completed,
        "last_event": run.last_event,
        "model": run.model,
        "event_count": run.event_count,
        "notes": notes,
        "source": "derived",
        "derived_from": "codex_logs",
        "analysis_window_minutes": analysis_window_minutes,
        "threshold_seconds": stuck_threshold_seconds,
    }


def grafana_headers() -> dict[str, str]:
    user = os.environ.get("GRAFANA_USER", "admin")
    password = os.environ.get("GRAFANA_PASSWORD", "admin")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    request_headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} from {url}: {detail[:300]}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach {url}: {error.reason}") from error
    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


def logql_quote(value: str) -> str:
    return json.dumps(value)


def query_loki(
    grafana_url: str,
    service_name: str,
    env_filter: str | None,
    window_minutes: int,
    limit: int,
    now: dt.datetime,
) -> dict[str, Any]:
    query = "{" + f"service_name={logql_quote(service_name)}" + "}"
    query += ' | conversation_id != ""'
    if env_filter:
        query += f" | env={logql_quote(env_filter)}"
    end_ns = int(now.timestamp() * 1_000_000_000)
    start_ns = int((now - dt.timedelta(minutes=window_minutes)).timestamp() * 1_000_000_000)
    params = urllib.parse.urlencode(
        {
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": str(limit),
            "direction": "forward",
        }
    )
    base = grafana_url.rstrip("/")
    url = f"{base}/api/datasources/proxy/uid/loki/loki/api/v1/query_range?{params}"
    return http_json(url, headers=grafana_headers())


def safe_events_from_loki(
    response: dict[str, Any], hash_key: str | None
) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    value_count = 0
    results = response.get("data", {}).get("result", [])
    for stream in results:
        labels = stream.get("stream", {})
        raw_identifier = labels.pop("conversation_id", None)
        if not raw_identifier:
            labels.clear()
            continue
        run_hash = hash_run_identifier(str(raw_identifier), hash_key)
        raw_identifier = None
        for value in stream.get("values", []):
            value_count += 1
            event_name = str(labels.get("event_name", "unknown"))
            event_kind = str(labels.get("event_kind", ""))
            event: dict[str, Any] = {
                "run_hash": run_hash,
                "timestamp": parse_loki_timestamp(str(value[0])),
                "event_name": event_name if event_name in MEANINGFUL_EVENTS else "unknown",
                "event_kind": event_kind if event_kind == "response.completed" else "",
                "model": str(labels.get("model", "")),
            }
            events.append(event)
        # Discard all remaining source metadata, including arguments/output.
        labels.clear()
    return events, value_count


def aggregate_events(events: Iterable[dict[str, Any]]) -> list[RunAggregate]:
    runs: dict[str, RunAggregate] = {}
    for event in events:
        run_hash = event["run_hash"]
        if run_hash not in runs:
            runs[run_hash] = RunAggregate(
                run_hash=run_hash,
                first_seen=event["timestamp"],
                last_seen=event["timestamp"],
            )
        runs[run_hash].add_event(event)
    return sorted(runs.values(), key=lambda item: item.last_seen, reverse=True)


def otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    return {"stringValue": str(value)}


def build_otlp_logs(rows: list[dict[str, Any]], emitted_at: dt.datetime) -> dict[str, Any]:
    timestamp_ns = str(int(emitted_at.timestamp() * 1_000_000_000))
    log_records = []
    for row in rows:
        attributes = {"event_name": DERIVED_EVENT_NAME, **row}
        log_records.append(
            {
                "timeUnixNano": timestamp_ns,
                "observedTimeUnixNano": timestamp_ns,
                "severityNumber": 9,
                "severityText": "INFO",
                "body": {"stringValue": json.dumps(row, separators=(",", ":"), sort_keys=True)},
                "attributes": [
                    {"key": key, "value": otlp_value(value)}
                    for key, value in attributes.items()
                ],
            }
        )
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": DERIVED_SERVICE_NAME}},
                        {"key": "source", "value": {"stringValue": "derived"}},
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "codex.run_health", "version": "1"},
                        "logRecords": log_records,
                    }
                ],
            }
        ]
    }


def assert_log_only_emission(endpoint: str, payload: dict[str, Any]) -> None:
    parsed = urllib.parse.urlparse(endpoint)
    if not parsed.path.endswith("/v1/logs"):
        raise RuntimeError("Derived emission is restricted to an OTLP /v1/logs endpoint.")
    serialized = json.dumps(payload, separators=(",", ":"))
    if '"resourceMetrics"' in serialized or '"metric"' in serialized:
        raise RuntimeError("Native/Prometheus metric emission is forbidden in Phase 2.")
    if DERIVED_EVENT_NAME not in serialized:
        raise RuntimeError("Derived payload is missing the codex.run_health event label.")
    # Guard names are allowed only as source log event values, never as output
    # metric descriptors. The OTLP payload above contains no metrics section.
    _ = FORBIDDEN_NATIVE_METRICS


def emit_derived(rows: list[dict[str, Any]], endpoint: str) -> None:
    if not rows:
        return
    payload = build_otlp_logs(rows, utc_now())
    assert_log_only_emission(endpoint, payload)
    http_json(endpoint, method="POST", body=payload)


def write_output(rows: list[dict[str, Any]], output_path: str) -> None:
    path = pathlib.Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def format_summary(rows: list[dict[str, Any]], window_minutes: int) -> str:
    counts = {
        state: sum(1 for row in rows if row["state"] == state)
        for state in (
            COMPLETED_RECENTLY,
            SLOW_BUT_ALIVE,
            STUCK_CANDIDATE,
            UNKNOWN_INCOMPLETE,
        )
    }
    lines = [
        "Codex Stuck Triage",
        "",
        f"Analysis window: last {window_minutes} minutes",
        f"Runs analyzed: {len(rows)}",
        f"Completed recently: {counts[COMPLETED_RECENTLY]}",
        f"Slow but alive: {counts[SLOW_BUT_ALIVE]}",
        f"Stuck candidates: {counts[STUCK_CANDIDATE]}",
        f"Unknown incomplete: {counts[UNKNOWN_INCOMPLETE]}",
    ]

    urgent_states = {STUCK_CANDIDATE, UNKNOWN_INCOMPLETE}
    urgent = sorted(
        (row for row in rows if row["state"] in urgent_states),
        key=lambda row: (row["state"] != STUCK_CANDIDATE, -row["quiet_for_seconds"]),
    )[:5]
    if urgent:
        lines.extend(["", "Top urgent rows:"])
        lines.extend(
            f"- {row['state']} run_hash={row['run_hash']} "
            f"quiet_for_seconds={row['quiet_for_seconds']}"
            for row in urgent
        )

    if rows and counts[COMPLETED_RECENTLY] == len(rows):
        lines.extend(
            [
                "",
                "Healthy outcome:",
                "No stuck or incomplete runs were found in this analysis window.",
                "If the Grafana triage table is empty, that means there are no active "
                "incomplete runs to show.",
            ]
        )
    elif not rows:
        lines.extend(
            [
                "",
                "No runs were found in this analysis window.",
                "Check the selected service, environment filter, time range, and OTLP pipeline.",
            ]
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify privacy-safe Codex stuck candidates from local Loki logs."
    )
    parser.add_argument("--window-minutes", type=int, default=360)
    parser.add_argument("--alive-threshold-seconds", type=int, default=120)
    parser.add_argument("--stuck-threshold-seconds", type=int, default=600)
    parser.add_argument("--grafana-url", default="http://localhost:3000")
    parser.add_argument("--service-name", default=os.environ.get("CODEX_SERVICE_NAME", DEFAULT_SERVICE_NAME))
    parser.add_argument("--env-filter")
    parser.add_argument("--emit-derived", action="store_true")
    parser.add_argument("--otlp-logs-url", default="http://localhost:4318/v1/logs")
    parser.add_argument("--output-json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--loki-limit", type=int, default=5000)
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    for name in ("window_minutes", "alive_threshold_seconds", "stuck_threshold_seconds", "loki_limit"):
        if getattr(args, name) <= 0:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if args.alive_threshold_seconds >= args.stuck_threshold_seconds:
        raise ValueError("--alive-threshold-seconds must be less than --stuck-threshold-seconds")
    if args.dry_run and args.emit_derived:
        raise ValueError("--dry-run and --emit-derived cannot be used together")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_args(args)
        hash_key = os.environ.get("CODEX_RUN_HEALTH_HASH_KEY")
        if not hash_key:
            print(
                "WARNING: CODEX_RUN_HEALTH_HASH_KEY is unset; using plain SHA-256. HMAC-SHA256 is preferred.",
                file=sys.stderr,
            )
        now = utc_now()
        response = query_loki(
            args.grafana_url,
            args.service_name,
            args.env_filter,
            args.window_minutes,
            args.loki_limit,
            now,
        )
        events, value_count = safe_events_from_loki(response, hash_key)
        if value_count >= args.loki_limit:
            print(
                f"WARNING: Loki returned the configured limit ({args.loki_limit}); results may be truncated.",
                file=sys.stderr,
            )
        runs = aggregate_events(events)
        rows = [
            classify_run(
                run,
                now,
                args.alive_threshold_seconds,
                args.stuck_threshold_seconds,
                args.window_minutes,
            )
            for run in runs
        ]
        if args.output_json:
            write_output(rows, args.output_json)
        if args.emit_derived:
            emit_derived(rows, args.otlp_logs_url)
        print(format_summary(rows, args.window_minutes))
        return 0
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
