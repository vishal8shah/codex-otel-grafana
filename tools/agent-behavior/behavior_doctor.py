#!/usr/bin/env python3
"""Validate the local behaviour-monitor policy, hooks, stack, and provisioning."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from behavior_common import ANALYZER_HEARTBEAT_EVENT, FINDING_SERVICE, load_policy
from behavior_hooks import check as check_hooks


REPO_ROOT = Path(__file__).resolve().parents[2]


def reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            response.read(32)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, TimeoutError):
        return False


def recent_analyzer_heartbeat(grafana_url: str, minutes: int) -> bool:
    query = (
        f'count_over_time({{service_name={json.dumps(FINDING_SERVICE)}}} '
        f'| event_name={json.dumps(ANALYZER_HEARTBEAT_EVENT)} [{minutes}m])'
    )
    params = urllib.parse.urlencode({"query": query})
    user = os.environ.get("GRAFANA_USER", "admin")
    password = os.environ.get("GRAFANA_PASSWORD", "admin")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = urllib.request.Request(
        f"{grafana_url.rstrip('/')}/api/datasources/proxy/uid/loki/loki/api/v1/query?{params}",
        headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("data", {}).get("result"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the local Codex behaviour-monitor setup.")
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--grafana-url", default="http://localhost:3000")
    parser.add_argument("--collector-health-url", default="http://localhost:4318/")
    parser.add_argument("--heartbeat-max-age-minutes", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    checks = {}
    try:
        policy = load_policy(root / "tools" / "agent-behavior" / "policy.json")
        checks["policy"] = policy["default_mode"] == "observe"
    except (ValueError, OSError):
        checks["policy"] = False
    checks["hooks"] = check_hooks(root) == 0
    dashboard = root / "observability" / "dashboards" / "codex-agent-behavior-security.json"
    try:
        checks["dashboard"] = json.loads(dashboard.read_text(encoding="utf-8")).get("uid") == "codex-agent-behavior-security"
    except (OSError, json.JSONDecodeError):
        checks["dashboard"] = False
    checks["grafana"] = reachable(f"{args.grafana_url.rstrip('/')}/api/health")
    checks["collector"] = reachable(args.collector_health_url)
    checks["loki_analyzer_heartbeat"] = checks["grafana"] and recent_analyzer_heartbeat(
        args.grafana_url, args.heartbeat_max_age_minutes
    )
    alert = root / "observability" / "provisioning" / "alerting" / "behavior-notification.yaml"
    try:
        alert_payload = json.loads(alert.read_text(encoding="utf-8"))
        checks["alert"] = bool(alert_payload.get("groups"))
    except (OSError, json.JSONDecodeError):
        checks["alert"] = False
    for name, ok in checks.items():
        print(f"{'OK' if ok else 'MISSING'}: {name}")
    print("Heartbeat/no-data status must be checked in Grafana; alert silence is not health evidence.")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
