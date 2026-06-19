#!/usr/bin/env python3
"""Emit one focused synthetic Codex-like API reliability scenario."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import uuid
from typing import Any

from api_reliability import http_json, otlp_value, utc_now


DEFAULT_ENV = "synthetic-api-reliability-phase4"
RAW_SERVICE_NAME = "Codex Desktop"
RAW_EVENT_NAME = "codex.api_request"


def nanoseconds(value: dt.datetime) -> str:
    return str(int(value.timestamp() * 1_000_000_000))


def log_record(timestamp: dt.datetime, attributes: dict[str, Any]) -> dict[str, Any]:
    if attributes.get("event_name") != RAW_EVENT_NAME:
        raise ValueError("Synthetic source event is not the schema-confirmed API event.")
    return {
        "timeUnixNano": nanoseconds(timestamp),
        "observedTimeUnixNano": nanoseconds(utc_now()),
        "severityNumber": 9,
        "severityText": "INFO",
        "body": {"stringValue": ""},
        "attributes": [{"key": key, "value": otlp_value(value)} for key, value in attributes.items()],
    }


def build_synthetic_payload(now: dt.datetime, env_name: str) -> dict[str, Any]:
    # The source identifier and endpoint exist only in raw synthetic telemetry.
    # The analyzer hashes both before producing any derived record.
    shared = {
        "event_name": RAW_EVENT_NAME,
        "conversation_id": str(uuid.uuid4()),
        "endpoint": "/v1/responses",
        "env": env_name,
        "synthetic": True,
        "synthetic.scenario": "failed-retried-slow-api-request",
        "synthetic.run_id": f"api-proof-{uuid.uuid4().hex[:12]}",
    }
    records = [
        log_record(
            now - dt.timedelta(seconds=20),
            {**shared, "duration_ms": 900, "http_response_status_code": 503, "success": False, "attempt": 1},
        ),
        log_record(
            now - dt.timedelta(seconds=10),
            {**shared, "duration_ms": 12_500, "http_response_status_code": 503, "success": False, "attempt": 2},
        ),
    ]
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": RAW_SERVICE_NAME}}]},
                "scopeLogs": [{"scope": {"name": "codex.synthetic_api_reliability", "version": "1"}, "logRecords": records}],
            }
        ]
    }


def validate_payload(endpoint: str, payload: dict[str, Any]) -> None:
    if not urllib.parse.urlparse(endpoint).path.endswith("/v1/logs"):
        raise ValueError("Synthetic trigger is restricted to an OTLP /v1/logs endpoint.")
    serialized = json.dumps(payload, separators=(",", ":"))
    if '"resourceMetrics"' in serialized or '"metric"' in serialized:
        raise ValueError("Synthetic validation must not emit native or Prometheus metrics.")
    if "codex.api_diagnostic" in serialized:
        raise ValueError("Synthetic validation must emit raw source events, not derived rows.")
    for required in (
        '"key":"synthetic","value":{"boolValue":true}',
        '"key":"synthetic.scenario"',
        '"key":"synthetic.run_id"',
    ):
        if required not in serialized:
            raise ValueError("Synthetic payload is missing required scenario tags.")
    for unsafe in ("prompt", "user_email", "user_account_id", "api_key", "cwd", "arguments", "output", "tool_name", "call_id"):
        if f'"key":"{unsafe}"' in serialized:
            raise ValueError("Synthetic payload contains an unsafe field.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit one failed, retried, and slow API source scenario through OTLP logs.")
    parser.add_argument("--otlp-logs-url", default="http://localhost:4318/v1/logs")
    parser.add_argument("--env", default=DEFAULT_ENV)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.env.startswith("synthetic-api-reliability-"):
        print("ERROR: --env must start with synthetic-api-reliability-", file=sys.stderr)
        return 1
    try:
        payload = build_synthetic_payload(utc_now(), args.env)
        validate_payload(args.otlp_logs_url, payload)
        http_json(args.otlp_logs_url, method="POST", body=payload)
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Emitted 2 synthetic raw API log records for 1 run/endpoint group in env={args.env}; no derived rows or metrics emitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
