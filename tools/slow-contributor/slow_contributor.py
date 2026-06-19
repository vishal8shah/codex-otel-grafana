#!/usr/bin/env python3
"""Privacy-safe slow contributor triage from schema-confirmed Codex logs."""

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


SLOW_API_CONTRIBUTOR = "SLOW_API_CONTRIBUTOR"
SLOW_TOOL_CONTRIBUTOR = "SLOW_TOOL_CONTRIBUTOR"
MULTIPLE_SLOW_CONTRIBUTORS = "MULTIPLE_SLOW_CONTRIBUTORS"

API_EVENT = "codex.api_request"
TOOL_EVENT = "codex.tool_result"
ALLOWED_EVENTS = {API_EVENT, TOOL_EVENT}
DERIVED_EVENT_NAME = "codex.slow_contributor"
DERIVED_SERVICE_NAME = "Codex Slow Contributor Diagnosis"
DEFAULT_SERVICE_NAME = "Codex Desktop"
DEFAULT_API_THRESHOLD_MS = 10_000
DEFAULT_TOOL_THRESHOLD_MS = 10_000
MISSING_ENDPOINT_SENTINEL = "__endpoint_not_observed__"

FORBIDDEN_NATIVE_METRICS = (
    "codex.api_request",
    "codex.api_request.duration_ms",
    "codex.sse_event",
    "codex.sse_event.duration_ms",
    "codex.tool.call",
    "codex.tool.call.duration_ms",
)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_loki_timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(value) / 1_000_000_000, tz=dt.timezone.utc)


def parse_nonnegative_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def hash_identifier(raw_identifier: str, key: str | None) -> str:
    encoded = raw_identifier.encode("utf-8")
    if key:
        return hmac.new(key.encode("utf-8"), encoded, hashlib.sha256).hexdigest()
    return hashlib.sha256(encoded).hexdigest()


@dataclasses.dataclass
class ContributorAggregate:
    run_hash: str
    contributor_type: str
    endpoint_hash: str
    tool_name: str
    first_seen: dt.datetime
    last_seen: dt.datetime
    event_count: int = 0
    max_duration_ms: int = 0

    def add_event(self, event: dict[str, Any]) -> None:
        self.first_seen = min(self.first_seen, event["timestamp"])
        self.last_seen = max(self.last_seen, event["timestamp"])
        self.event_count += 1
        self.max_duration_ms = max(self.max_duration_ms, event["duration_ms"])


def contributor_threshold(item: ContributorAggregate, api_ms: int, tool_ms: int) -> int:
    return api_ms if item.contributor_type == "api_request" else tool_ms


def classify_contributors(
    aggregates: Iterable[ContributorAggregate],
    analysis_window_minutes: int,
    api_threshold_ms: int,
    tool_threshold_ms: int,
) -> list[dict[str, Any]]:
    slow: list[tuple[ContributorAggregate, int]] = []
    for item in aggregates:
        threshold = contributor_threshold(item, api_threshold_ms, tool_threshold_ms)
        if item.max_duration_ms > threshold:
            slow.append((item, threshold))

    counts_by_run: dict[str, int] = {}
    for item, _ in slow:
        counts_by_run[item.run_hash] = counts_by_run.get(item.run_hash, 0) + 1

    rows = []
    for item, threshold in slow:
        if counts_by_run[item.run_hash] > 1:
            state = MULTIPLE_SLOW_CONTRIBUTORS
            notes = "More than one confirmed slow contributor group was observed for this run in the selected window."
        elif item.contributor_type == "api_request":
            state = SLOW_API_CONTRIBUTOR
            notes = "API request duration exceeded the configured local contributor threshold."
        else:
            state = SLOW_TOOL_CONTRIBUTOR
            notes = "Tool result duration exceeded the configured local contributor threshold."
        rows.append(
            {
                "run_hash": item.run_hash,
                "contributor_type": item.contributor_type,
                "endpoint_hash": item.endpoint_hash,
                "tool_name": item.tool_name,
                "state": state,
                "first_seen": iso_utc(item.first_seen),
                "last_seen": iso_utc(item.last_seen),
                "duration_ms": item.max_duration_ms,
                "threshold_ms": threshold,
                "event_count": item.event_count,
                "analysis_window_minutes": analysis_window_minutes,
                "grouping_precision": "run_endpoint" if item.contributor_type == "api_request" else "run_tool",
                "notes": notes,
                "source": "derived",
                "derived_from": "schema_confirmed_api_and_tool_logs",
            }
        )
    return sorted(rows, key=lambda row: (row["duration_ms"], row["last_seen"]), reverse=True)


def grafana_headers() -> dict[str, str]:
    user = os.environ.get("GRAFANA_USER", "admin")
    password = os.environ.get("GRAFANA_PASSWORD", "admin")
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
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
        data = json.dumps(body, separators=(",", ":")).encode()
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
    return json.loads(payload.decode()) if payload else {}


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
    query += ' | conversation_id != "" | event_name=~"codex.api_request|codex.tool_result"'
    if env_filter:
        query += f" | env={logql_quote(env_filter)}"
    params = urllib.parse.urlencode(
        {
            "query": query,
            "start": str(int((now - dt.timedelta(minutes=window_minutes)).timestamp() * 1e9)),
            "end": str(int(now.timestamp() * 1e9)),
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
        raw_run = labels.pop("conversation_id", None)
        raw_endpoint = labels.pop("endpoint", None)
        event_name = str(labels.get("event_name", ""))
        duration_ms = parse_nonnegative_int(labels.get("duration_ms"))
        if not raw_run or event_name not in ALLOWED_EVENTS or duration_ms is None:
            labels.clear()
            continue
        run_hash = hash_identifier(str(raw_run), hash_key)
        if event_name == API_EVENT:
            contributor_type = "api_request"
            endpoint_hash = hash_identifier(
                str(raw_endpoint).strip() if raw_endpoint else MISSING_ENDPOINT_SENTINEL,
                hash_key,
            )
            tool_name = ""
        else:
            contributor_type = "tool_result"
            endpoint_hash = ""
            tool_name = str(labels.get("tool_name", "")).strip()
            if not tool_name:
                labels.clear()
                continue
        for value in stream.get("values", []):
            value_count += 1
            events.append(
                {
                    "run_hash": run_hash,
                    "contributor_type": contributor_type,
                    "endpoint_hash": endpoint_hash,
                    "tool_name": tool_name,
                    "duration_ms": duration_ms,
                    "timestamp": parse_loki_timestamp(str(value[0])),
                }
            )
        raw_run = None
        raw_endpoint = None
        labels.clear()
    return events, value_count


def aggregate_events(events: Iterable[dict[str, Any]]) -> list[ContributorAggregate]:
    aggregates: dict[tuple[str, str, str, str], ContributorAggregate] = {}
    for event in events:
        key = (event["run_hash"], event["contributor_type"], event["endpoint_hash"], event["tool_name"])
        if key not in aggregates:
            aggregates[key] = ContributorAggregate(
                run_hash=event["run_hash"],
                contributor_type=event["contributor_type"],
                endpoint_hash=event["endpoint_hash"],
                tool_name=event["tool_name"],
                first_seen=event["timestamp"],
                last_seen=event["timestamp"],
            )
        aggregates[key].add_event(event)
    return list(aggregates.values())


def otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    return {"stringValue": str(value)}


def build_otlp_logs(rows: list[dict[str, Any]], emitted_at: dt.datetime) -> dict[str, Any]:
    timestamp_ns = str(int(emitted_at.timestamp() * 1e9))
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
                "attributes": [{"key": key, "value": otlp_value(value)} for key, value in attributes.items()],
            }
        )
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": [
                    {"key": "service.name", "value": {"stringValue": DERIVED_SERVICE_NAME}},
                    {"key": "source", "value": {"stringValue": "derived"}},
                ]},
                "scopeLogs": [{"scope": {"name": DERIVED_EVENT_NAME, "version": "1"}, "logRecords": records}],
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
        raise RuntimeError("Derived payload is missing the slow contributor event label.")
    _ = FORBIDDEN_NATIVE_METRICS


def emit_derived(rows: list[dict[str, Any]], endpoint: str) -> None:
    if rows:
        payload = build_otlp_logs(rows, utc_now())
        assert_log_only_emission(endpoint, payload)
        http_json(endpoint, method="POST", body=payload)


def write_output(rows: list[dict[str, Any]], output_path: str) -> None:
    path = pathlib.Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def format_summary(rows: list[dict[str, Any]], window: int, api_ms: int, tool_ms: int) -> str:
    api_count = sum(row["contributor_type"] == "api_request" for row in rows)
    tool_count = sum(row["contributor_type"] == "tool_result" for row in rows)
    multiple_runs = len({row["run_hash"] for row in rows if row["state"] == MULTIPLE_SLOW_CONTRIBUTORS})
    lines = [
        "Codex Slow Contributor Triage",
        "",
        f"Analysis window: last {window} minutes",
        f"Local API threshold: {api_ms} ms",
        f"Local tool threshold: {tool_ms} ms",
        f"Slow contributor groups: {len(rows)}",
        f"Slow API groups: {api_count}",
        f"Slow tool groups: {tool_count}",
        f"Runs with multiple slow contributors: {multiple_runs}",
        "This does not measure full end-to-end Codex turn latency.",
    ]
    if rows:
        lines.extend(["", "Top contributor rows:"])
        lines.extend(
            f"- {row['state']} contributor_type={row['contributor_type']} duration_ms={row['duration_ms']} "
            f"run_hash={row['run_hash']} endpoint_hash={row['endpoint_hash']} tool_name={row['tool_name']}"
            for row in rows[:5]
        )
    else:
        lines.extend(["", "No confirmed contributor exceeded its local threshold in this window."])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify slow confirmed Codex API and tool contributors from local Loki logs.")
    parser.add_argument("--window-minutes", type=int, default=360)
    parser.add_argument("--api-slow-threshold-ms", type=int, default=DEFAULT_API_THRESHOLD_MS)
    parser.add_argument("--tool-slow-threshold-ms", type=int, default=DEFAULT_TOOL_THRESHOLD_MS)
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
    for name in ("window_minutes", "api_slow_threshold_ms", "tool_slow_threshold_ms", "loki_limit"):
        if getattr(args, name) <= 0:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if args.dry_run and args.emit_derived:
        raise ValueError("--dry-run and --emit-derived cannot be used together")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_args(args)
        hash_key = os.environ.get("CODEX_SLOW_CONTRIBUTOR_HASH_KEY")
        if not hash_key:
            print(
                "WARNING: CODEX_SLOW_CONTRIBUTOR_HASH_KEY is unset; run and endpoint identifiers will use plain SHA-256. HMAC-SHA256 is preferred.",
                file=sys.stderr,
            )
        now = utc_now()
        response = query_loki(args.grafana_url, args.service_name, args.env_filter, args.window_minutes, args.loki_limit, now)
        events, value_count = safe_events_from_loki(response, hash_key)
        if value_count >= args.loki_limit:
            print(f"WARNING: Loki returned the configured limit ({args.loki_limit}); results may be truncated.", file=sys.stderr)
        rows = classify_contributors(
            aggregate_events(events),
            args.window_minutes,
            args.api_slow_threshold_ms,
            args.tool_slow_threshold_ms,
        )
        if args.output_json:
            write_output(rows, args.output_json)
        if args.emit_derived:
            emit_derived(rows, args.otlp_logs_url)
        print(format_summary(rows, args.window_minutes, args.api_slow_threshold_ms, args.tool_slow_threshold_ms))
        return 0
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
