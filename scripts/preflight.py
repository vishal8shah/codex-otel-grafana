#!/usr/bin/env python3
"""Actionable, local-only prerequisite checks for the onboarding proof."""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "docker-compose.yml",
    "scripts/start.ps1",
    "scripts/stop.ps1",
    "scripts/health-check.py",
    "scripts/run-onboarding-demo.py",
    "scripts/emit-demo-scenarios.py",
    "docs/onboarding.html",
)
LOCAL_PORTS = (3000, 4317, 4318)
EXPECTED_CONTAINER = "codex-otel-lgtm"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    action: str = ""


def run(command: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def expected_container_running(docker: str) -> bool:
    result = run([docker, "ps", "--filter", f"name=^/{EXPECTED_CONTAINER}$", "--format", "{{.Names}}"])
    return result.returncode == 0 and EXPECTED_CONTAINER in result.stdout.splitlines()


def collect_checks() -> list[Check]:
    checks = [
        Check(
            "Python",
            sys.version_info >= (3, 10),
            f"{sys.version.split()[0]} at {sys.executable}",
            "Install Python 3.10 or newer, then rerun this command.",
        )
    ]
    docker = shutil.which("docker")
    checks.append(Check("Docker CLI", bool(docker), docker or "not found", "Install Docker Desktop or Docker Engine."))
    daemon_ok = False
    compose_ok = False
    running = False
    if docker:
        info = run([docker, "info"])
        daemon_ok = info.returncode == 0
        checks.append(Check("Docker daemon", daemon_ok, "reachable" if daemon_ok else "not reachable", "Start Docker Desktop or the Docker daemon."))
        compose = run([docker, "compose", "version"])
        compose_ok = compose.returncode == 0
        detail = (compose.stdout or compose.stderr).strip().splitlines()
        checks.append(Check("Docker Compose", compose_ok, detail[0] if detail else "not available", "Install the Docker Compose plugin."))
        if daemon_ok:
            running = expected_container_running(docker)
    else:
        checks.extend(
            (
                Check("Docker daemon", False, "not checked", "Install and start Docker."),
                Check("Docker Compose", False, "not checked", "Install the Docker Compose plugin."),
            )
        )

    for port in LOCAL_PORTS:
        occupied = port_open(port)
        if not occupied:
            checks.append(Check(f"Port {port}", True, "available"))
        elif running:
            checks.append(Check(f"Port {port}", True, f"in use by the existing {EXPECTED_CONTAINER} stack"))
        else:
            checks.append(
                Check(
                    f"Port {port}",
                    False,
                    "already in use by another process",
                    f"Stop the conflicting process or set the documented local port override before starting the stack.",
                )
            )

    for relative in REQUIRED_FILES:
        checks.append(Check(f"Repository file {relative}", (REPO_ROOT / relative).is_file(), "present" if (REPO_ROOT / relative).is_file() else "missing", "Restore the file from the repository."))
    checks.append(Check("Secrets", True, "none required for the local synthetic proof"))
    return checks


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check local prerequisites without installing or contacting external services.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    print("Codex Observability Diagnostic Kit onboarding preflight")
    print("Local checks only; this command installs nothing and requires no secrets.\n")
    checks = collect_checks()
    for check in checks:
        print(f"[{'PASS' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
        if not check.ok and check.action:
            print(f"       Next: {check.action}")
    failures = [check for check in checks if not check.ok]
    print(f"\nPreflight {'passed' if not failures else 'failed'}: {len(checks) - len(failures)}/{len(checks)} checks passed.")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
