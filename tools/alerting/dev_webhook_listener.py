#!/usr/bin/env python3
"""Capture a privacy-reduced local Grafana alert notification for development proof."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


ALLOWED_PATH = "/grafana-alerts"
SAFE_HASH = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_KEYS = {
    "arguments",
    "call_id",
    "conversation_id",
    "cwd",
    "endpoint",
    "identity",
    "input_messages",
    "last_assistant_message",
    "output",
    "prompt",
    "raw_endpoint",
    "tool_output",
    "user_account_id",
    "user_email",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                found.add(normalized)
            found.update(find_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(find_forbidden_keys(child))
    return found


def safe_notification(payload: dict[str, Any]) -> dict[str, Any]:
    forbidden = find_forbidden_keys(payload)
    if forbidden:
        raise ValueError(f"notification contains forbidden keys: {', '.join(sorted(forbidden))}")

    alerts = payload.get("alerts")
    if not isinstance(alerts, list):
        raise ValueError("notification alerts must be a list")

    safe_alerts: list[dict[str, str]] = []
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
        run_hash = str(labels.get("run_hash", ""))
        if run_hash and not SAFE_HASH.fullmatch(run_hash):
            raise ValueError("run_hash is not a 64-character hexadecimal privacy-safe hash")
        safe_alert: dict[str, str] = {
            "alert_name": str(labels.get("alertname", "Codex stuck candidate detected")),
            "status": str(alert.get("status", payload.get("status", "unknown"))),
        }
        state = str(labels.get("state", ""))
        if state:
            safe_alert["state"] = state
        if run_hash:
            safe_alert["run_hash"] = run_hash
        safe_alerts.append(safe_alert)

    return {
        "received_at": utc_now(),
        "receiver": "Codex local dev webhook",
        "status": str(payload.get("status", "unknown")),
        "alert_count": len(safe_alerts),
        "alerts": safe_alerts,
        "dashboard": "http://localhost:3000/d/codex-stuck-burn-triage/codex-stuck-burn-triage",
        "playbook": "https://vishal8shah.github.io/codex-otel-grafana/#playbook",
    }


class AlertHandler(BaseHTTPRequestHandler):
    server_version = "CodexDevAlertReceiver/1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != ALLOWED_PATH:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > self.server.max_body_bytes:  # type: ignore[attr-defined]
                raise ValueError("notification body size is invalid")
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("notification must be a JSON object")
            record = safe_notification(payload)
            output_path: pathlib.Path = self.server.output_path  # type: ignore[attr-defined]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
            print(json.dumps(record, separators=(",", ":"), sort_keys=True), flush=True)
            self.send_response(204)
            self.end_headers()
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            print(f"Rejected notification: {error}", flush=True)
            self.send_error(400, str(error))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Receive local Grafana webhook proof safely.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9087)
    parser.add_argument(
        "--output-jsonl",
        default="alert-receiver-output/notifications.jsonl",
        help="Gitignored path for privacy-reduced captured notifications.",
    )
    parser.add_argument("--max-body-bytes", type=int, default=1_000_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.port <= 65535 or args.max_body_bytes <= 0:
        raise SystemExit("port and max body size must be positive")
    server = ThreadingHTTPServer((args.host, args.port), AlertHandler)
    server.output_path = pathlib.Path(args.output_jsonl).expanduser()  # type: ignore[attr-defined]
    server.max_body_bytes = args.max_body_bytes  # type: ignore[attr-defined]
    print(
        f"Local development webhook listening on http://{args.host}:{args.port}{ALLOWED_PATH}; "
        f"safe capture={server.output_path}. Press Ctrl+C to stop.",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Local development webhook stopped.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
