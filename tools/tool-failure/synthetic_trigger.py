#!/usr/bin/env python3
"""Emit one minimal synthetic Codex-like failed-tool scenario through OTLP logs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import uuid
from typing import Any

from tool_failure import http_json, otlp_value, utc_now


DEFAULT_ENV = "synthetic-tool-failure-phase3"
RAW_SERVICE_NAME = "Codex Desktop"
SYNTHETIC_TOOL_NAME = "synthetic_tool"
ALLOWED_EVENT_NAMES = {"codex.tool_decision", "codex.tool_result"}


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


def build_synthetic_payload(now: dt.datetime, env_name: str) -> dict[str, Any]:
    # This fake source identifier exists only in the raw OTLP payload and is
    # never printed. The analyzer hashes it before producing derived records.
    source_identifier = str(uuid.uuid4())
    safe_run_id = f"failed-tool-{uuid.uuid4().hex[:12]}"
    shared = {
        "conversation_id": source_identifier,
        "env": env_name,
        "synthetic": True,
        "synthetic.scenario": "failed-tool-result",
        "synthetic.run_id": safe_run_id,
        "tool_name": SYNTHETIC_TOOL_NAME,
    }
    records = [
        log_record(
            now - dt.timedelta(seconds=20),
            {"event_name": "codex.tool_decision", **shared},
        ),
        log_record(
            now - dt.timedelta(seconds=10),
            {
                "event_name": "codex.tool_result",
                **shared,
                "success": False,
                "duration_ms": 750,
            },
        ),
    ]
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
                        "scope": {"name": "codex.synthetic_tool_failure", "version": "1"},
                        "logRecords": records,
                    }
                ],
            }
        ]
    }


def validate_payload(endpoint: str, payload: dict[str, Any]) -> None:
    if not urllib.parse.urlparse(endpoint).path.endswith("/v1/logs"):
        raise ValueError("Synthetic trigger is restricted to an OTLP /v1/logs endpoint.")
    serialized = json.dumps(payload, separators=(",", ":"))
    if '"resourceMetrics"' in serialized or '"metric"' in serialized:
        raise ValueError("Synthetic validation must not emit native or Prometheus metrics.")
    if "codex.tool_diagnostic" in serialized:
        raise ValueError("Synthetic validation must emit raw source events, not derived rows.")
    required = (
        '"key":"synthetic","value":{"boolValue":true}',
        '"key":"synthetic.scenario"',
        '"key":"synthetic.run_id"',
    )
    if not all(marker in serialized for marker in required):
        raise ValueError("Synthetic payload is missing required scenario tags.")
    forbidden = (
        "prompt",
        "user_email",
        "user_account_id",
        "api_key",
        "call_id",
        "arguments",
        "output",
        "cwd",
    )
    if any(f'"key":"{name}"' in serialized for name in forbidden):
        raise ValueError("Synthetic payload contains an unsafe field.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit one failed-tool source scenario through OTLP logs."
    )
    parser.add_argument("--otlp-logs-url", default="http://localhost:4318/v1/logs")
    parser.add_argument("--env", default=DEFAULT_ENV)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.env.startswith("synthetic-tool-failure-"):
        print("ERROR: --env must start with synthetic-tool-failure-", file=sys.stderr)
        return 1
    try:
        payload = build_synthetic_payload(utc_now(), args.env)
        validate_payload(args.otlp_logs_url, payload)
        http_json(args.otlp_logs_url, method="POST", body=payload)
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Emitted 2 synthetic source log records for 1 tool/run pair in env={args.env}; "
        "no derived rows or metrics emitted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
