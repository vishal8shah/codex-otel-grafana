#!/usr/bin/env python3
"""Validate the local behaviour-monitor policy, hooks, stack, and provisioning."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from behavior_common import load_policy
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the local Codex behaviour-monitor setup.")
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--grafana-url", default="http://localhost:3000")
    parser.add_argument("--collector-health-url", default="http://localhost:4318/")
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
    for name, ok in checks.items():
        print(f"{'OK' if ok else 'MISSING'}: {name}")
    print("Heartbeat/no-data status must be checked in Grafana; alert silence is not health evidence.")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
