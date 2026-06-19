#!/usr/bin/env python3
"""Emit one focused synthetic slow API/tool contributor scenario."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import uuid
from typing import Any

from slow_contributor import http_json, otlp_value, utc_now


DEFAULT_ENV = "synthetic-slow-contributor-phase5"
RAW_SERVICE_NAME = "Codex Desktop"
ALLOWED_EVENTS = {"codex.api_request", "codex.tool_result"}


def nanoseconds(value: dt.datetime) -> str:
    return str(int(value.timestamp() * 1_000_000_000))


def log_record(timestamp: dt.datetime, attributes: dict[str, Any]) -> dict[str, Any]:
    if attributes.get("event_name") not in ALLOWED_EVENTS:
        raise ValueError("Synthetic source event is outside the schema-confirmed allowlist.")
    return {
        "timeUnixNano": nanoseconds(timestamp),
        "observedTimeUnixNano": nanoseconds(utc_now()),
        "severityNumber": 9,
        "severityText": "INFO",
        "body": {"stringValue": ""},
        "attributes": [{"key": key, "value": otlp_value(value)} for key, value in attributes.items()],
    }


def build_synthetic_payload(now: dt.datetime, env_name: str) -> dict[str, Any]:
    source_run = str(uuid.uuid4())
    shared = {
        "conversation_id": source_run,
        "env": env_name,
        "synthetic": True,
        "synthetic.scenario": "multiple-slow-contributors",
        "synthetic.run_id": f"slow-proof-{uuid.uuid4().hex[:12]}",
    }
    records = [
        log_record(
            now - dt.timedelta(seconds=20),
            {
                **shared,
                "event_name": "codex.api_request",
                "endpoint": "/v1/responses",
                "duration_ms": 15_000,
                "http_response_status_code": 200,
                "success": True,
                "attempt": 1,
            },
        ),
        log_record(
            now - dt.timedelta(seconds=10),
            {
                **shared,
                "event_name": "codex.tool_result",
                "tool_name": "synthetic_slow_tool",
                "duration_ms": 12_000,
                "success": True,
            },
        ),
    ]
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": RAW_SERVICE_NAME}}]},
                "scopeLogs": [{"scope": {"name": "codex.synthetic_slow_contributor", "version": "1"}, "logRecords": records}],
            }
        ]
    }


def validate_payload(endpoint: str, payload: dict[str, Any]) -> None:
    if not urllib.parse.urlparse(endpoint).path.endswith("/v1/logs"):
        raise ValueError("Synthetic trigger is restricted to an OTLP /v1/logs endpoint.")
    serialized = json.dumps(payload, separators=(",", ":"))
    if '"resourceMetrics"' in serialized or '"metric"' in serialized:
        raise ValueError("Synthetic validation must not emit native or Prometheus metrics.")
    if "codex.slow_contributor" in serialized:
        raise ValueError("Synthetic validation must emit raw source events, not derived rows.")
    for required in ('"key":"synthetic","value":{"boolValue":true}', '"key":"synthetic.scenario"', '"key":"synthetic.run_id"'):
        if required not in serialized:
            raise ValueError("Synthetic payload is missing required scenario tags.")
    for unsafe in ("prompt", "user_email", "user_account_id", "api_key", "cwd", "arguments", "output", "call_id"):
        if f'"key":"{unsafe}"' in serialized:
            raise ValueError("Synthetic payload contains an unsafe field.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit one slow API and slow tool source scenario through OTLP logs.")
    parser.add_argument("--otlp-logs-url", default="http://localhost:4318/v1/logs")
    parser.add_argument("--env", default=DEFAULT_ENV)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.env.startswith("synthetic-slow-contributor-"):
        print("ERROR: --env must start with synthetic-slow-contributor-", file=sys.stderr)
        return 1
    try:
        payload = build_synthetic_payload(utc_now(), args.env)
        validate_payload(args.otlp_logs_url, payload)
        http_json(args.otlp_logs_url, method="POST", body=payload)
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Emitted 2 synthetic raw contributor records for 1 run in env={args.env}; no derived rows or metrics emitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
