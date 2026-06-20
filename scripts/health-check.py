#!/usr/bin/env python3
"""Verify the repository-owned local LGTM stack through loopback endpoints."""

from __future__ import annotations

import argparse
import base64
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


EXPECTED_CONTAINER = "codex-otel-lgtm"
DATASOURCES = ("loki", "tempo", "prometheus")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def local_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise argparse.ArgumentTypeError("Grafana URL must use localhost, 127.0.0.1, or ::1")
    return value.rstrip("/")


def get_json(url: str, user: str, password: str, timeout: float = 5) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def tcp_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def container_health() -> Check:
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", EXPECTED_CONTAINER],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return Check("LGTM container", False, "Docker unavailable or timed out")
    detail = result.stdout.strip() or result.stderr.strip() or "not found"
    ready = result.returncode == 0 and detail in {"running", "running healthy"}
    return Check("LGTM container", ready, detail)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check local Grafana, datasources, and OTLP receiver readiness.")
    parser.add_argument("--grafana-url", type=local_url, default="http://localhost:3000")
    parser.add_argument("--grafana-user", default="admin")
    parser.add_argument("--grafana-password", default="admin")
    parser.add_argument("--wait-seconds", type=int, default=60, help="Wait for startup readiness before failing.")
    return parser.parse_args(argv)


def collect_checks(args: argparse.Namespace) -> list[Check]:
    checks = [container_health()]
    try:
        health = get_json(f"{args.grafana_url}/api/health", args.grafana_user, args.grafana_password)
        checks.append(Check("Grafana", health.get("database") == "ok", f"{args.grafana_url} database={health.get('database', 'unknown')}"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        checks.append(Check("Grafana", False, f"unreachable: {error}"))

    for uid in DATASOURCES:
        try:
            health = get_json(f"{args.grafana_url}/api/datasources/uid/{uid}/health", args.grafana_user, args.grafana_password)
            checks.append(Check(f"Datasource {uid}", str(health.get("status", "")).upper() == "OK", str(health.get("message", "no message"))))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            checks.append(Check(f"Datasource {uid}", False, f"unreachable: {error}"))

    checks.extend((Check("OTLP HTTP", tcp_open(4318), "127.0.0.1:4318"), Check("OTLP gRPC", tcp_open(4317), "127.0.0.1:4317")))
    return checks


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.wait_seconds < 0 or args.wait_seconds > 300:
        print("ERROR: --wait-seconds must be between 0 and 300", file=sys.stderr)
        return 1
    deadline = time.monotonic() + args.wait_seconds
    while True:
        checks = collect_checks(args)
        if all(check.ok for check in checks) or time.monotonic() >= deadline:
            break
        time.sleep(2)
    print("Codex Observability Diagnostic Kit local stack health\n")
    for check in checks:
        print(f"[{'PASS' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
    failures = [check for check in checks if not check.ok]
    if failures:
        print("\nHealth check failed. Start the stack with .\\scripts\\start.ps1, then rerun this command.")
        return 1
    print("\nLocal stack is ready.")
    print(f"Grafana: {args.grafana_url}")
    print(f"Command Center: {args.grafana_url}/d/codex-diagnostic-command-center/codex-diagnostic-command-center?orgId=1&from=now-30m&to=now")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
