#!/usr/bin/env python3
"""Emit one minimal synthetic Codex-like stuck scenario through OTLP logs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import uuid
from typing import Any

from run_health import http_json, otlp_value, utc_now


DEFAULT_ENV = "synthetic-stuck-phase2"
RAW_SERVICE_NAME = "Codex Desktop"
ALLOWED_EVENT_NAMES = {
    "codex.conversation_starts",
    "codex.api_request",
}


def nanoseconds(value: dt.datetime) -> str:
    return str(int(value.timestamp() * 1_000_000_000))


def log_record(timestamp: dt.datetime, attributes: dict[str, Any]) -> dict[str, Any]:
    if attributes.get("event_name") not in ALLOWED_EVENT_NAMES:
        raise ValueError("Synthetic source event is not in the schema-confirmed allowlist.")
    return {
        "timeUnixNano": nanoseconds(timestamp),
        "observedTimeUnixNano": nanoseconds(utc_now()),
        "severityNumber": 9,
        "severityText": "INFO",
        "body": {"stringValue": ""},
        "attributes": [
            {"key": key, "value": otlp_value(value)} for key, value in attributes.items()
        ],
    }


def build_synthetic_payload(
    now: dt.datetime, env_name: str, stuck_quiet_seconds: int
) -> dict[str, Any]:
    # Ephemeral fake identifiers are never printed or written by this tool.
    stuck_identifier = str(uuid.uuid4())
    suffix = uuid.uuid4().hex[:12]
    stuck_run_id = f"stuck-candidate-{suffix}"
    stuck_last = now - dt.timedelta(seconds=stuck_quiet_seconds)

    stuck_records = [
        log_record(
            stuck_last - dt.timedelta(seconds=60),
            {
                "event_name": "codex.conversation_starts",
                "conversation_id": stuck_identifier,
                "env": env_name,
                "synthetic": True,
                "synthetic.scenario": "stuck-candidate",
                "synthetic.run_id": stuck_run_id,
                "model": "synthetic-validation",
            },
        ),
        log_record(
            stuck_last,
            {
                "event_name": "codex.api_request",
                "conversation_id": stuck_identifier,
                "env": env_name,
                "synthetic": True,
                "synthetic.scenario": "stuck-candidate",
                "synthetic.run_id": stuck_run_id,
                "model": "synthetic-validation",
                "duration_ms": 250,
                "http_response_status_code": 200,
                "success": True,
                "endpoint": "responses",
                "attempt": 1,
            },
        ),
    ]
    records = stuck_records
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": RAW_SERVICE_NAME}}
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "codex.synthetic_validation", "version": "1"},
                        "logRecords": records,
                    }
                ],
            }
        ]
    }


def validate_payload(endpoint: str, payload: dict[str, Any]) -> None:
    if not urllib.parse.urlparse(endpoint).path.endswith("/v1/logs"):
        raise ValueError("Synthetic triggers are restricted to an OTLP /v1/logs endpoint.")
    serialized = json.dumps(payload, separators=(",", ":"))
    if '"resourceMetrics"' in serialized or '"metric"' in serialized:
        raise ValueError("Synthetic validation must not emit native or Prometheus metrics.")
    if "codex.run_health" in serialized:
        raise ValueError("Synthetic validation must emit raw source events, not derived rows.")
    if not all(
        marker in serialized
        for marker in (
            '"key":"synthetic","value":{"boolValue":true}',
            '"key":"synthetic.scenario"',
            '"key":"synthetic.run_id"',
        )
    ):
        raise ValueError("Synthetic validation payload is missing required scenario tags.")
    forbidden = ("prompt", "user_email", "user_account_id", "arguments", "output", "cwd")
    if any(f'"key":"{name}"' in serialized for name in forbidden):
        raise ValueError("Synthetic payload contains an unsafe field.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit one stuck-candidate source scenario through OTLP logs."
    )
    parser.add_argument("--otlp-logs-url", default="http://localhost:4318/v1/logs")
    parser.add_argument("--env", default=DEFAULT_ENV)
    parser.add_argument("--stuck-quiet-seconds", type=int, default=660)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.env.startswith("synthetic-stuck-"):
        print("ERROR: --env must start with synthetic-stuck-", file=sys.stderr)
        return 1
    if args.stuck_quiet_seconds < 600:
        print("ERROR: --stuck-quiet-seconds must be at least 600", file=sys.stderr)
        return 1
    try:
        payload = build_synthetic_payload(utc_now(), args.env, args.stuck_quiet_seconds)
        validate_payload(args.otlp_logs_url, payload)
        http_json(args.otlp_logs_url, method="POST", body=payload)
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Emitted 2 synthetic source log records for 1 run in env={args.env} "
        "scenario=stuck-candidate; no derived rows or metrics emitted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
