#!/usr/bin/env python3
"""Privacy-safe API request reliability diagnosis from confirmed Codex logs."""

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


FAILED_REQUEST = "FAILED_REQUEST"
RETRIED_REQUEST = "RETRIED_REQUEST"
SLOW_REQUEST = "SLOW_REQUEST"
SUCCESSFUL_REQUEST = "SUCCESSFUL_REQUEST"
UNKNOWN_REQUEST = "UNKNOWN_REQUEST"
STATE_ORDER = (
    FAILED_REQUEST,
    RETRIED_REQUEST,
    SLOW_REQUEST,
    SUCCESSFUL_REQUEST,
    UNKNOWN_REQUEST,
)

RAW_EVENT_NAME = "codex.api_request"
DERIVED_EVENT_NAME = "codex.api_diagnostic"
DERIVED_SERVICE_NAME = "Codex API Diagnosis"
DEFAULT_SERVICE_NAME = "Codex Desktop"
DEFAULT_SLOW_THRESHOLD_MS = 10_000
MISSING_ENDPOINT_SENTINEL = "__endpoint_not_observed__"

# These are native metric names documented or tested elsewhere. This analyzer
# emits OTLP logs only and never registers or emits any of them.
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
    return parsed if parsed >= 0 else None


def hash_identifier(raw_identifier: str, key: str | None) -> str:
    encoded = raw_identifier.encode("utf-8")
    if key:
        return hmac.new(key.encode("utf-8"), encoded, hashlib.sha256).hexdigest()
    return hashlib.sha256(encoded).hexdigest()


def status_bucket(value: Any) -> str:
    code = parse_nonnegative_int(value)
    if code is None:
        return "unknown"
    if 100 <= code <= 599:
        return f"{code // 100}xx"
    return "other"


STATUS_PRIORITY = {"5xx": 6, "4xx": 5, "3xx": 4, "2xx": 3, "1xx": 2, "other": 1, "unknown": 0}


@dataclasses.dataclass
class ApiAggregate:
    run_hash: str
    endpoint_hash: str
    first_seen: dt.datetime
    last_seen: dt.datetime
    event_count: int = 0
    failed_evidence_count: int = 0
    successful_evidence_count: int = 0
    unknown_outcome_count: int = 0
    max_duration_ms: int = 0
    max_attempt: int = 0
    status_bucket: str = "unknown"

    def add_event(self, event: dict[str, Any]) -> None:
        self.first_seen = min(self.first_seen, event["timestamp"])
        self.last_seen = max(self.last_seen, event["timestamp"])
        self.event_count += 1
        duration = event.get("duration_ms")
        if duration is not None:
            self.max_duration_ms = max(self.max_duration_ms, duration)
        attempt = event.get("attempt")
        if attempt is not None:
            self.max_attempt = max(self.max_attempt, attempt)
        bucket = event["status_bucket"]
        if STATUS_PRIORITY[bucket] > STATUS_PRIORITY[self.status_bucket]:
            self.status_bucket = bucket

        failed = event.get("success") is False or bucket in {"4xx", "5xx"}
        successful = event.get("success") is True or bucket == "2xx"
        if failed:
            self.failed_evidence_count += 1
        elif successful:
            self.successful_evidence_count += 1
        else:
            self.unknown_outcome_count += 1


def classify_api(
    item: ApiAggregate, analysis_window_minutes: int, slow_threshold_ms: int
) -> dict[str, Any]:
    retry_observed = item.max_attempt > 1
    slow_observed = item.max_duration_ms > slow_threshold_ms
    if item.failed_evidence_count:
        state = FAILED_REQUEST
        notes = "Failed API request evidence was observed in this run/endpoint group."
    elif retry_observed:
        state = RETRIED_REQUEST
        notes = "Attempt evidence above 1 was observed in this run/endpoint group."
    elif slow_observed:
        state = SLOW_REQUEST
        notes = "Observed duration exceeded the configured local investigation threshold."
    elif item.successful_evidence_count:
        state = SUCCESSFUL_REQUEST
        notes = "Successful API request evidence was observed with no higher-priority issue state."
    else:
        state = UNKNOWN_REQUEST
        notes = "API request evidence was observed, but outcome evidence was incomplete."

    return {
        "run_hash": item.run_hash,
        "endpoint_hash": item.endpoint_hash,
        "state": state,
        "first_seen": iso_utc(item.first_seen),
        "last_seen": iso_utc(item.last_seen),
        "event_count": item.event_count,
        "failed_evidence_count": item.failed_evidence_count,
        "successful_evidence_count": item.successful_evidence_count,
        "unknown_outcome_count": item.unknown_outcome_count,
        "max_duration_ms": item.max_duration_ms,
        "max_attempt": item.max_attempt,
        "retry_observed": retry_observed,
        "slow_observed": slow_observed,
        "status_bucket": item.status_bucket,
        "slow_threshold_ms": slow_threshold_ms,
        "analysis_window_minutes": analysis_window_minutes,
        "notes": notes,
        "source": "derived",
        "derived_from": "codex_api_request_logs",
        "grouping_precision": "run_endpoint",
    }


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
    query += ' | conversation_id != "" | event_name="codex.api_request"'
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
        raw_run_identifier = labels.pop("conversation_id", None)
        raw_endpoint = labels.pop("endpoint", None)
        event_name = str(labels.get("event_name", ""))
        if not raw_run_identifier or event_name != RAW_EVENT_NAME:
            labels.clear()
            continue
        run_hash = hash_identifier(str(raw_run_identifier), hash_key)
        endpoint_hash = hash_identifier(
            str(raw_endpoint).strip() if raw_endpoint else MISSING_ENDPOINT_SENTINEL,
            hash_key,
        )
        for value in stream.get("values", []):
            value_count += 1
            events.append(
                {
                    "run_hash": run_hash,
                    "endpoint_hash": endpoint_hash,
                    "timestamp": parse_loki_timestamp(str(value[0])),
                    "success": parse_bool(labels.get("success")),
                    "duration_ms": parse_nonnegative_int(labels.get("duration_ms")),
                    "attempt": parse_nonnegative_int(labels.get("attempt")),
                    "status_bucket": status_bucket(labels.get("http_response_status_code")),
                }
            )
        # Drop endpoint, conversation_id, bodies, and every non-allowlisted label.
        raw_run_identifier = None
        raw_endpoint = None
        labels.clear()
    return events, value_count


def aggregate_events(events: Iterable[dict[str, Any]]) -> list[ApiAggregate]:
    aggregates: dict[tuple[str, str], ApiAggregate] = {}
    for event in events:
        key = (event["run_hash"], event["endpoint_hash"])
        if key not in aggregates:
            aggregates[key] = ApiAggregate(
                run_hash=event["run_hash"],
                endpoint_hash=event["endpoint_hash"],
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
        raise RuntimeError("Derived payload is missing the API diagnostic event label.")
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


def format_summary(rows: list[dict[str, Any]], window_minutes: int, slow_threshold_ms: int) -> str:
    counts = {state: sum(row["state"] == state for row in rows) for state in STATE_ORDER}
    lines = [
        "Codex API Request Reliability",
        "",
        f"Analysis window: last {window_minutes} minutes",
        f"Local slow threshold: {slow_threshold_ms} ms",
        f"Run/endpoint groups analyzed: {len(rows)}",
        f"Failed groups: {counts[FAILED_REQUEST]}",
        f"Retried-state groups: {counts[RETRIED_REQUEST]}",
        f"Groups with retry evidence: {sum(row['retry_observed'] for row in rows)}",
        f"Slow-state groups: {counts[SLOW_REQUEST]}",
        f"Groups over the slow threshold: {sum(row['slow_observed'] for row in rows)}",
        f"Successful groups: {counts[SUCCESSFUL_REQUEST]}",
        f"Unknown groups: {counts[UNKNOWN_REQUEST]}",
    ]
    issue_rows = [row for row in rows if row["state"] in {FAILED_REQUEST, RETRIED_REQUEST, SLOW_REQUEST, UNKNOWN_REQUEST}]
    if issue_rows:
        lines.extend(["", "Top investigation rows:"])
        lines.extend(
            f"- {row['state']} run_hash={row['run_hash']} endpoint_hash={row['endpoint_hash']} "
            f"status_bucket={row['status_bucket']} max_attempt={row['max_attempt']}"
            for row in issue_rows[:5]
        )
    elif rows:
        lines.extend(["", "No failed, retried, slow, or unknown API groups were found."])
    else:
        lines.extend(["", "No API request activity was found in this analysis window."])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify privacy-safe Codex API request evidence from local Loki logs.")
    parser.add_argument("--window-minutes", type=int, default=360)
    parser.add_argument("--slow-threshold-ms", type=int, default=DEFAULT_SLOW_THRESHOLD_MS)
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
    for name in ("window_minutes", "slow_threshold_ms", "loki_limit"):
        if getattr(args, name) <= 0:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if args.dry_run and args.emit_derived:
        raise ValueError("--dry-run and --emit-derived cannot be used together")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_args(args)
        hash_key = os.environ.get("CODEX_API_DIAG_HASH_KEY")
        if not hash_key:
            print(
                "WARNING: CODEX_API_DIAG_HASH_KEY is unset; run and endpoint identifiers will use plain SHA-256. HMAC-SHA256 is preferred.",
                file=sys.stderr,
            )
        now = utc_now()
        response = query_loki(args.grafana_url, args.service_name, args.env_filter, args.window_minutes, args.loki_limit, now)
        events, value_count = safe_events_from_loki(response, hash_key)
        if value_count >= args.loki_limit:
            print(f"WARNING: Loki returned the configured limit ({args.loki_limit}); results may be truncated.", file=sys.stderr)
        rows = [classify_api(item, args.window_minutes, args.slow_threshold_ms) for item in aggregate_events(events)]
        if args.output_json:
            write_output(rows, args.output_json)
        if args.emit_derived:
            emit_derived(rows, args.otlp_logs_url)
        print(format_summary(rows, args.window_minutes, args.slow_threshold_ms))
        return 0
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
