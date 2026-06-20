#!/usr/bin/env python3
"""Run and verify the existing walkthrough-rich proof through Loki and Grafana."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SCRIPT = REPO_ROOT / "scripts" / "emit-demo-scenarios.py"
HEALTH_SCRIPT = REPO_ROOT / "scripts" / "health-check.py"
COMMAND_CENTER_DASHBOARD = REPO_ROOT / "observability" / "dashboards" / "codex-diagnostic-command-center.json"


@dataclass(frozen=True)
class Contract:
    service: str
    event: str
    group_fields: tuple[str, ...]
    dashboard: str
    dashboard_path: str


CONTRACTS = {
    "run_health": Contract("Codex Run Health", "codex.run_health", ("run_hash",), "Codex Stuck Triage", "codex-stuck-burn-triage/codex-stuck-burn-triage"),
    "tool_failure": Contract("Codex Tool Diagnosis", "codex.tool_diagnostic", ("run_hash", "tool_name"), "Codex Tool Failure Diagnosis", "codex-tool-failure-diagnosis/codex-tool-failure-diagnosis"),
    "api_reliability": Contract("Codex API Diagnosis", "codex.api_diagnostic", ("run_hash", "endpoint_hash"), "Codex API Request Reliability", "codex-api-request-reliability/codex-api-request-reliability"),
    "slow_contributor": Contract("Codex Slow Contributor Diagnosis", "codex.slow_contributor", ("run_hash", "contributor_type", "endpoint_hash", "tool_name"), "Codex Slow Contributor Triage", "codex-slow-contributor-triage/codex-slow-contributor-triage"),
}


def local_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise argparse.ArgumentTypeError("Grafana URL must use localhost, 127.0.0.1, or ::1")
    return value.rstrip("/")


def headers(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def get_json(url: str, user: str, password: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers(user, password))
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} from local Grafana: {detail[:300]}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach local Grafana: {error.reason}") from error


def command_center_issue_states() -> dict[str, set[str]]:
    dashboard = json.loads(COMMAND_CENTER_DASHBOARD.read_text(encoding="utf-8"))
    states: dict[str, set[str]] = {}
    for name, contract in CONTRACTS.items():
        for panel in dashboard.get("panels", []):
            for target in panel.get("targets", []):
                expression = str(target.get("expr", ""))
                if f'service_name="{contract.service}"' not in expression or f'event_name="{contract.event}"' not in expression:
                    continue
                match = re.search(r'state=~"([^"]+)"', expression)
                if match:
                    states[name] = set(match.group(1).split("|"))
    missing = sorted(set(CONTRACTS) - set(states))
    if missing:
        raise RuntimeError(f"Command Center state filters are missing for: {', '.join(missing)}")
    return states


def group_key(labels: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(labels.get(field, "")) for field in fields)


def query_groups(
    grafana_url: str,
    contract: Contract,
    start: dt.datetime,
    user: str,
    password: str,
) -> dict[tuple[str, ...], set[str]]:
    query = f'{{service_name={json.dumps(contract.service)}}} | event_name={json.dumps(contract.event)}'
    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)
    params = urllib.parse.urlencode(
        {
            "query": query,
            "start": str(int(start.timestamp() * 1_000_000_000)),
            "end": str(int(now.timestamp() * 1_000_000_000)),
            "limit": "5000",
            "direction": "forward",
        }
    )
    url = f"{grafana_url}/api/datasources/proxy/uid/loki/loki/api/v1/query_range?{params}"
    response = get_json(url, user, password)
    observed: dict[tuple[str, ...], set[str]] = {}
    for result in response.get("data", {}).get("result", []):
        labels = result.get("stream", {})
        key = group_key(labels, contract.group_fields)
        observed.setdefault(key, set()).add(str(labels.get("state", "")))
    return observed


def expected_groups(report: dict[str, Any], name: str, contract: Contract) -> dict[tuple[str, ...], str]:
    groups = report["diagnostics"][name].get("privacy_safe_groups", [])
    expected = {group_key(group, contract.group_fields): str(group.get("state", "")) for group in groups}
    declared = int(report["diagnostics"][name]["unique_groups_expected"])
    if len(expected) != declared:
        raise RuntimeError(f"{name}: profile declares {declared} groups but exposes {len(expected)} privacy-safe keys")
    return expected


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit and verify the walkthrough-rich local onboarding proof.")
    parser.add_argument("--grafana-url", type=local_url, default="http://localhost:3000")
    parser.add_argument("--grafana-user", default=os.environ.get("GRAFANA_USER", "admin"))
    parser.add_argument("--grafana-password", default=os.environ.get("GRAFANA_PASSWORD", "admin"))
    parser.add_argument("--window", default="30m")
    parser.add_argument("--wait-seconds", type=int, default=60)
    parser.add_argument("--report-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.wait_seconds < 10:
        print("ERROR: --wait-seconds must be at least 10", file=sys.stderr)
        return 1
    print("Checking the local stack before emitting synthetic evidence...")
    health = subprocess.run(
        [
            sys.executable,
            str(HEALTH_SCRIPT),
            "--grafana-url",
            args.grafana_url,
            "--grafana-user",
            args.grafana_user,
            "--grafana-password",
            args.grafana_password,
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    if health.returncode:
        return health.returncode

    started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    with tempfile.TemporaryDirectory(prefix="codex-onboarding-") as temp_dir:
        emitter_report = Path(temp_dir) / "emitter-report.json"
        command = [
            sys.executable,
            str(DEMO_SCRIPT),
            "--profile",
            "walkthrough-rich",
            "--window",
            args.window,
            "--grafana-url",
            args.grafana_url,
            "--report-json",
            str(emitter_report),
        ]
        print("\nRunning existing walkthrough-rich emitter and shipped analyzers:")
        print(" ".join(command[:-1] + ["<temporary-report.json>"]))
        completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
        if completed.returncode:
            return completed.returncode
        report = json.loads(emitter_report.read_text(encoding="utf-8"))

    issue_states = command_center_issue_states()
    expected_by_name = {name: expected_groups(report, name, contract) for name, contract in CONTRACTS.items()}
    deadline = time.monotonic() + args.wait_seconds
    observed_by_name: dict[str, dict[tuple[str, ...], set[str]]] = {}
    while time.monotonic() < deadline:
        observed_by_name = {
            name: query_groups(args.grafana_url, contract, started, args.grafana_user, args.grafana_password)
            for name, contract in CONTRACTS.items()
        }
        if all(set(expected_by_name[name]).issubset(observed_by_name[name]) for name in CONTRACTS):
            break
        time.sleep(2)
    else:
        missing = {
            name: len(set(expected_by_name[name]) - set(observed_by_name.get(name, {})))
            for name in CONTRACTS
        }
        print(f"ERROR: derived groups did not arrive before timeout: {missing}", file=sys.stderr)
        return 1

    proof: dict[str, Any] = {"profile": report["profile"], "proof_path": report["proof_path"], "diagnostics": {}}
    print("\nExpected profile groups vs observed Loki groups:")
    print("Diagnostic          Expected  Observed  Command Center issues")
    for name, contract in CONTRACTS.items():
        expected = expected_by_name[name]
        relevant_observed = {key: observed_by_name[name][key] for key in expected}
        expected_issues = sum(state in issue_states[name] for state in expected.values())
        observed_issues = sum(bool(states.intersection(issue_states[name])) for states in relevant_observed.values())
        if len(relevant_observed) != len(expected) or observed_issues != expected_issues:
            print(f"ERROR: {name} expected/observed mismatch", file=sys.stderr)
            return 1
        print(f"{name:20} {len(expected):8}  {len(relevant_observed):8}  {observed_issues:8}")
        proof["diagnostics"][name] = {
            "expected_unique_groups": len(expected),
            "observed_unique_groups": len(relevant_observed),
            "expected_command_center_issues": expected_issues,
            "observed_command_center_issues": observed_issues,
            "dashboard": contract.dashboard,
        }

    base = args.grafana_url
    command_center_url = f"{base}/d/codex-diagnostic-command-center/codex-diagnostic-command-center?orgId=1&from=now-30m&to=now"
    proof["command_center_url"] = command_center_url
    print(f"\nCommand Center: {command_center_url}")
    print("Expected focused dashboards:")
    for contract in CONTRACTS.values():
        print(f"- {contract.dashboard}: {base}/d/{contract.dashboard_path}?orgId=1&from=now-30m&to=now")
    print("\nSUCCESS: synthetic source evidence reached Loki, shipped analyzers emitted derived records, and Loki returned every expected privacy-safe group.")
    print("This proves the local synthetic investigation path. It does not prove system health, identify a product bug, or operate a production environment.")

    if args.report_json:
        path = Path(args.report_json).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Proof report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
