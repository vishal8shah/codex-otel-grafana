#!/usr/bin/env python3
"""Privacy-safe tool failure diagnosis from schema-confirmed Codex logs."""

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


FAILED_RESULT = "FAILED_RESULT"
SUCCESSFUL_RESULT = "SUCCESSFUL_RESULT"
SELECTED_NO_RESULT = "SELECTED_NO_RESULT"
UNKNOWN_RESULT = "UNKNOWN_RESULT"

DERIVED_EVENT_NAME = "codex.tool_diagnostic"
DERIVED_SERVICE_NAME = "Codex Tool Diagnosis"
DEFAULT_SERVICE_NAME = "Codex Desktop"
TOOL_DECISION_EVENT = "codex.tool_decision"
TOOL_RESULT_EVENT = "codex.tool_result"
ALLOWED_EVENTS = {TOOL_DECISION_EVENT, TOOL_RESULT_EVENT}

# This analyzer emits OTLP logs only. These native metric names are never
# registered or emitted by this feature.
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


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_loki_timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(value) / 1_000_000_000, tz=dt.timezone.utc)


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def parse_nonnegative_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, parsed)


def hash_run_identifier(raw_identifier: str, key: str | None) -> str:
    encoded = raw_identifier.encode("utf-8")
    if key:
        return hmac.new(key.encode("utf-8"), encoded, hashlib.sha256).hexdigest()
    return hashlib.sha256(encoded).hexdigest()


@dataclasses.dataclass
class ToolAggregate:
    run_hash: str
    tool_name: str
    first_seen: dt.datetime
    last_seen: dt.datetime
    last_event: str = "unknown"
    decision_count: int = 0
    result_count: int = 0
    successful_results: int = 0
    failed_results: int = 0
    unknown_results: int = 0
    latest_duration_ms: int | None = None

    def add_event(self, event: dict[str, Any]) -> None:
        timestamp = event["timestamp"]
        self.first_seen = min(self.first_seen, timestamp)
        if timestamp >= self.last_seen:
            self.last_seen = timestamp
            self.last_event = event["event_name"]
            if event["event_name"] == TOOL_RESULT_EVENT:
                self.latest_duration_ms = event.get("duration_ms")

        if event["event_name"] == TOOL_DECISION_EVENT:
            self.decision_count += 1
            return

        self.result_count += 1
        if event.get("success") is True:
            self.successful_results += 1
        elif event.get("success") is False:
            self.failed_results += 1
        else:
            self.unknown_results += 1


def classify_tool(item: ToolAggregate, analysis_window_minutes: int) -> dict[str, Any]:
    if item.failed_results > 0:
        state = FAILED_RESULT
        result_state = "failed"
        notes = "At least one schema-confirmed tool result reported success=false."
    elif item.result_count > 0 and item.successful_results == item.result_count:
        state = SUCCESSFUL_RESULT
        result_state = "successful"
        notes = "All observed schema-confirmed tool results reported success=true."
    elif item.decision_count > 0 and item.result_count == 0:
        state = SELECTED_NO_RESULT
        result_state = "no_result_observed"
        notes = "A tool decision was observed without a matching tool result in this window."
    else:
        state = UNKNOWN_RESULT
        result_state = "unknown"
        notes = "Tool activity was observed, but confirmed result evidence is incomplete."

    return {
        "run_hash": item.run_hash,
        "tool_name": item.tool_name,
        "state": state,
        "result_state": result_state,
        "first_seen": iso_utc(item.first_seen),
        "last_seen": iso_utc(item.last_seen),
        "last_event": item.last_event,
        "decision_count": item.decision_count,
        "result_count": item.result_count,
        "successful_results": item.successful_results,
        "failed_results": item.failed_results,
        "unknown_results": item.unknown_results,
        "latest_duration_ms": item.latest_duration_ms or 0,
        "notes": notes,
        "source": "derived",
        "derived_from": "codex_tool_logs",
        "analysis_window_minutes": analysis_window_minutes,
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
    query += ' | event_name=~"codex.tool_decision|codex.tool_result"'
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
    for stream in response.get("data", {}).get("result", []):
        labels = stream.get("stream", {})
        raw_identifier = labels.pop("conversation_id", None)
        event_name = str(labels.get("event_name", ""))
        tool_name = str(labels.get("tool_name", "")).strip()
        if not raw_identifier or event_name not in ALLOWED_EVENTS or not tool_name:
            labels.clear()
            continue
        run_hash = hash_run_identifier(str(raw_identifier), hash_key)
        raw_identifier = None
        for value in stream.get("values", []):
            value_count += 1
            event = {
                "run_hash": run_hash,
                "tool_name": tool_name,
                "timestamp": parse_loki_timestamp(str(value[0])),
                "event_name": event_name,
                "success": parse_bool(labels.get("success")) if event_name == TOOL_RESULT_EVENT else None,
                "duration_ms": (
                    parse_nonnegative_int(labels.get("duration_ms"))
                    if event_name == TOOL_RESULT_EVENT
                    else None
                ),
            }
            events.append(event)
        # Drop call_id, arguments, output, paths, and every other source label.
        labels.clear()
    return events, value_count


def aggregate_events(events: Iterable[dict[str, Any]]) -> list[ToolAggregate]:
    aggregates: dict[tuple[str, str], ToolAggregate] = {}
    for event in events:
        key = (event["run_hash"], event["tool_name"])
        if key not in aggregates:
            aggregates[key] = ToolAggregate(
                run_hash=event["run_hash"],
                tool_name=event["tool_name"],
                first_seen=event["timestamp"],
                last_seen=event["timestamp"],
            )
        aggregates[key].add_event(event)
    return sorted(aggregates.values(), key=lambda item: item.last_seen, reverse=True)


def otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    return {"stringValue": str(value)}


def build_otlp_logs(rows: list[dict[str, Any]], emitted_at: dt.datetime) -> dict[str, Any]:
    timestamp_ns = str(int(emitted_at.timestamp() * 1_000_000_000))
    records = []
    for row in rows:
        attributes = {"event_name": DERIVED_EVENT_NAME, **row}
        records.append(
            {
                "timeUnixNano": timestamp_ns,
                "observedTimeUnixNano": timestamp_ns,
                "severityNumber": 9,
                "severityText": "INFO",
                "body": {"stringValue": json.dumps(row, separators=(",", ":"), sort_keys=True)},
                "attributes": [
                    {"key": key, "value": otlp_value(value)} for key, value in attributes.items()
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
                        "scope": {"name": DERIVED_EVENT_NAME, "version": "1"},
                        "logRecords": records,
                    }
                ],
            }
        ]
    }


def assert_log_only_emission(endpoint: str, payload: dict[str, Any]) -> None:
    if not urllib.parse.urlparse(endpoint).path.endswith("/v1/logs"):
        raise RuntimeError("Derived emission is restricted to an OTLP /v1/logs endpoint.")
    serialized = json.dumps(payload, separators=(",", ":"))
    if '"resourceMetrics"' in serialized or '"metric"' in serialized:
        raise RuntimeError("Native/Prometheus metric emission is forbidden.")
    if DERIVED_EVENT_NAME not in serialized:
        raise RuntimeError("Derived payload is missing the tool diagnostic event label.")
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
        for state in (FAILED_RESULT, SUCCESSFUL_RESULT, SELECTED_NO_RESULT, UNKNOWN_RESULT)
    }
    lines = [
        "Codex Tool Failure Diagnosis",
        "",
        f"Analysis window: last {window_minutes} minutes",
        f"Tool/run pairs analyzed: {len(rows)}",
        f"Failed results: {counts[FAILED_RESULT]}",
        f"Successful results: {counts[SUCCESSFUL_RESULT]}",
        f"Selected with no result: {counts[SELECTED_NO_RESULT]}",
        f"Unknown results: {counts[UNKNOWN_RESULT]}",
    ]
    urgent = sorted(
        (row for row in rows if row["state"] in {FAILED_RESULT, SELECTED_NO_RESULT, UNKNOWN_RESULT}),
        key=lambda row: (-row["failed_results"], row["state"], row["tool_name"]),
    )[:5]
    if urgent:
        lines.extend(["", "Top investigation rows:"])
        lines.extend(
            f"- {row['state']} tool_name={row['tool_name']} run_hash={row['run_hash']} "
            f"failed_results={row['failed_results']}"
            for row in urgent
        )
    elif rows:
        lines.extend(["", "Healthy outcome:", "No failed, missing, or unknown tool results were found."])
    else:
        lines.extend(["", "No tool activity was found in this analysis window."])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify privacy-safe Codex tool result evidence from local Loki logs."
    )
    parser.add_argument("--window-minutes", type=int, default=360)
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
    for name in ("window_minutes", "loki_limit"):
        if getattr(args, name) <= 0:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if args.dry_run and args.emit_derived:
        raise ValueError("--dry-run and --emit-derived cannot be used together")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_args(args)
        hash_key = os.environ.get("CODEX_TOOL_DIAG_HASH_KEY")
        if not hash_key:
            print(
                "WARNING: CODEX_TOOL_DIAG_HASH_KEY is unset; using plain SHA-256. HMAC-SHA256 is preferred.",
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
        rows = [classify_tool(item, args.window_minutes) for item in aggregate_events(events)]
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
