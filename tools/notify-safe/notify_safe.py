#!/usr/bin/env python3
"""Emit a privacy-reduced record from a Codex notify payload."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


def pseudonym(value: Any, namespace: str) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    key = os.environ.get("CODEX_NOTIFY_HASH_KEY")
    data = f"{namespace}\0{value}".encode("utf-8")
    if key:
        return hmac.new(key.encode("utf-8"), data, hashlib.sha256).hexdigest()
    return hashlib.sha256(data).hexdigest()


def project_basename(cwd: str) -> str:
    path_type = PureWindowsPath if "\\" in cwd else PurePosixPath
    return path_type(cwd).name


def load_payload() -> dict[str, Any]:
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("notify payload must be a JSON object")
    return payload


def main() -> int:
    try:
        payload = load_payload()
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"notify-safe: invalid JSON: {exc}", file=sys.stderr)
        return 2

    if payload.get("type") != "agent-turn-complete":
        return 0

    output: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "agent-turn-complete",
    }

    thread_hash = pseudonym(payload.get("thread-id"), "thread")
    if thread_hash:
        output["thread_hash"] = thread_hash

    turn_hash = pseudonym(payload.get("turn-id"), "turn")
    if turn_hash:
        output["turn_hash"] = turn_hash

    cwd = payload.get("cwd")
    cwd_hash = pseudonym(cwd, "cwd")
    if cwd_hash:
        output["cwd_hash"] = cwd_hash

    if (
        os.environ.get("CODEX_NOTIFY_INCLUDE_PROJECT_BASENAME") == "1"
        and isinstance(cwd, str)
        and cwd
    ):
        output["project_basename"] = project_basename(cwd)

    print(json.dumps(output, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
