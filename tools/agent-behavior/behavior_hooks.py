#!/usr/bin/env python3
"""Install, inspect, or remove the repository-local behaviour hook config."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import sys
from pathlib import Path
from typing import Any


EVENTS = (
    "SessionStart", "SessionEnd", "PreToolUse", "PostToolUse", "PermissionRequest",
    "SubagentStart", "SubagentStop", "PreCompact", "PostCompact", "Stop", "Interrupt",
)
MARKER = "behavior_monitor.py"
MARKER_STATUS = "Recording privacy-safe behaviour evidence"


def quote(value: Path) -> str:
    return f'"{value}"'


def handler(script: Path, key_file: Path, event: str = "PreToolUse") -> dict[str, Any]:
    python_executable = Path(sys.executable).resolve()
    invocation = f"{quote(python_executable)} {quote(script)} --hash-key-file {quote(key_file)}"
    return {
        "type": "command",
        "command": invocation,
        "command_windows": invocation,
        "timeout": 3 if event in {"SessionEnd", "Interrupt"} else 10,
        "statusMessage": MARKER_STATUS,
    }


def is_ours(item: dict[str, Any]) -> bool:
    commands = f"{item.get('command', '')} {item.get('command_windows', '')}"
    return item.get("statusMessage") == MARKER_STATUS and MARKER in commands


def load_hooks(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"description": "Repository-local Codex hooks.", "hooks": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("existing hook configuration is invalid") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("hooks", {}), dict):
        raise ValueError("existing hook configuration is invalid")
    payload.setdefault("hooks", {})
    return payload


def install(root: Path) -> None:
    config_dir = root / ".codex"
    config_dir.mkdir(parents=True, exist_ok=True)
    hooks_path = config_dir / "hooks.json"
    key_path = config_dir / "behavior-monitor.key"
    if not key_path.exists():
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(secrets.token_hex(32) + "\n")
    if os.name != "nt":
        key_path.chmod(0o600)
    payload = load_hooks(hooks_path)
    script = Path(__file__).with_name("behavior_monitor.py").resolve()
    for event in EVENTS:
        groups = payload["hooks"].setdefault(event, [])
        preserved = []
        for existing in groups:
            handlers = [item for item in existing.get("hooks", []) if not is_ours(item)]
            if handlers:
                updated = dict(existing)
                updated["hooks"] = handlers
                preserved.append(updated)
        groups = preserved
        group: dict[str, Any] = {"hooks": [handler(script, key_path.resolve(), event)]}
        if event in {"PreToolUse", "PostToolUse", "PermissionRequest"}:
            group["matcher"] = "*"
        groups.append(group)
        payload["hooks"][event] = groups
    hooks_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Installed observe-only behaviour hooks in {hooks_path}")
    print("Codex will request hook trust before running repository hooks.")


def check(root: Path) -> int:
    hooks_path = root / ".codex" / "hooks.json"
    key_path = root / ".codex" / "behavior-monitor.key"
    try:
        payload = load_hooks(hooks_path)
    except ValueError:
        print("INVALID: repository hook configuration could not be parsed.")
        return 1
    configured = {
        event for event, groups in payload.get("hooks", {}).items()
        if any(is_ours(item) for group in groups for item in group.get("hooks", []))
    }
    missing = sorted(set(EVENTS) - configured)
    key_valid = key_path.exists() and len(key_path.read_text(encoding="utf-8").strip()) >= 32
    if key_valid and os.name != "nt":
        key_valid = stat.S_IMODE(key_path.stat().st_mode) == 0o600
    if missing or not key_valid:
        print(f"INCOMPLETE: missing_hooks={','.join(missing) or 'none'} key_present={key_path.exists()}")
        return 1
    print(f"OK: {len(configured)} behaviour hook events configured; local HMAC key present.")
    return 0


def remove(root: Path) -> None:
    hooks_path = root / ".codex" / "hooks.json"
    key_path = root / ".codex" / "behavior-monitor.key"
    if hooks_path.exists():
        payload = load_hooks(hooks_path)
        for event in list(payload["hooks"]):
            kept = []
            for group in payload["hooks"][event]:
                handlers = [item for item in group.get("hooks", []) if not is_ours(item)]
                if handlers:
                    updated = dict(group)
                    updated["hooks"] = handlers
                    kept.append(updated)
            if kept:
                payload["hooks"][event] = kept
            else:
                payload["hooks"].pop(event, None)
        if payload["hooks"]:
            hooks_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        elif payload.get("description") == "Repository-local Codex hooks.":
            hooks_path.unlink()
        else:
            hooks_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if key_path.exists():
        key_path.unlink()
    print("Removed repository-local behaviour hook handlers and HMAC key.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage repository-local Codex behaviour hooks.")
    parser.add_argument("action", choices=("install", "check", "remove"))
    parser.add_argument("--root", default=".")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.action == "install":
            install(root)
            return 0
        if args.action == "check":
            return check(root)
        remove(root)
        return 0
    except (OSError, ValueError):
        print("ERROR: hook configuration could not be updated safely.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
