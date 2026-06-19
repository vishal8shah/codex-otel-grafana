#!/usr/bin/env python3
"""Validate the Command Center against shipped repo contracts."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "observability" / "dashboards" / "codex-diagnostic-command-center.json"
DATASOURCE_PATH = ROOT / "observability" / "provisioning" / "datasources" / "datasources.yml"

DETAIL_DASHBOARDS = {
    "Codex Stuck Triage": "codex-stuck-burn-triage.json",
    "Codex Tool Failure Diagnosis": "codex-tool-failure-diagnosis.json",
    "Codex API Request Reliability": "codex-api-request-reliability.json",
    "Codex Slow Contributor Triage": "codex-slow-contributor-triage.json",
}

STREAMS = {
    "Stuck / incomplete runs": {
        "module": "tools/run-health/run_health.py",
        "service": "DERIVED_SERVICE_NAME",
        "event": "DERIVED_EVENT_NAME",
        "states": ("SLOW_BUT_ALIVE", "STUCK_CANDIDATE", "UNKNOWN_INCOMPLETE"),
        "grouping": ("run_hash",),
    },
    "Tool issue groups": {
        "module": "tools/tool-failure/tool_failure.py",
        "service": "DERIVED_SERVICE_NAME",
        "event": "DERIVED_EVENT_NAME",
        "states": ("FAILED_RESULT", "SELECTED_NO_RESULT", "UNKNOWN_RESULT"),
        "grouping": ("run_hash", "tool_name"),
    },
    "API reliability groups": {
        "module": "tools/api-reliability/api_reliability.py",
        "service": "DERIVED_SERVICE_NAME",
        "event": "DERIVED_EVENT_NAME",
        "states": ("FAILED_REQUEST", "RETRIED_REQUEST", "SLOW_REQUEST", "UNKNOWN_REQUEST"),
        "grouping": ("run_hash", "endpoint_hash"),
    },
    "Slow contributor groups": {
        "module": "tools/slow-contributor/slow_contributor.py",
        "service": "DERIVED_SERVICE_NAME",
        "event": "DERIVED_EVENT_NAME",
        "states": ("SLOW_API_CONTRIBUTOR", "SLOW_TOOL_CONTRIBUTOR", "MULTIPLE_SLOW_CONTRIBUTORS"),
        "grouping": ("run_hash", "contributor_type", "endpoint_hash", "tool_name"),
    },
}

UNSAFE_QUERY_FIELDS = (
    "conversation_id",
    "call_id",
    "user_email",
    "user_account_id",
    "user_prompt",
    "tool_arguments",
    "tool_output",
    "raw_endpoint",
    "cwd",
)

FOCUSED_DOCS = (
    "README.md",
    "PHASES.md",
    "observability/README.md",
    "docs/index.html",
    "docs/builder-metrics.html",
    "docs/rebuild-guide.html",
    "docs/architecture-and-operations.html",
    "docs/publishing.html",
)


def string_constants(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            constants[target.id] = node.value.value
    return constants


def provisioned_loki_uid() -> str:
    text = DATASOURCE_PATH.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^\s*- name:\s*Loki\s*$.*?^\s*uid:\s*([^\s#]+)\s*$", text)
    if not match:
        raise AssertionError("Could not resolve the provisioned Loki datasource UID")
    return match.group(1)


def panel_by_title(dashboard: dict[str, Any], title: str) -> dict[str, Any]:
    matches = [panel for panel in dashboard.get("panels", []) if panel.get("title") == title]
    if len(matches) != 1:
        raise AssertionError(f"Expected one panel titled {title!r}, found {len(matches)}")
    return matches[0]


def main() -> int:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    loki_uid = provisioned_loki_uid()
    if dashboard.get("uid") != "codex-diagnostic-command-center":
        raise AssertionError("Unexpected Command Center dashboard UID")

    variable = next((item for item in dashboard.get("templating", {}).get("list", []) if item.get("name") == "lookback"), None)
    if not variable or variable.get("current", {}).get("value") != "6h":
        raise AssertionError("Command Center must expose a lookback variable with a 6h default")
    if dashboard.get("time") != {"from": "now-6h", "to": "now"}:
        raise AssertionError("Command Center time picker must align with the shipped 6h default")
    if dashboard.get("timepicker", {}).get("hidden") is not True:
        raise AssertionError("Command Center must expose only the shared lookback control")

    detail_contracts: dict[str, str] = {}
    for title, filename in DETAIL_DASHBOARDS.items():
        detail = json.loads((DASHBOARD_PATH.parent / filename).read_text(encoding="utf-8"))
        if detail.get("title") != title:
            raise AssertionError(f"Detailed dashboard title drifted for {filename}")
        detail_contracts[title] = str(detail.get("uid"))

    all_links = dashboard.get("links", [])
    for panel in dashboard.get("panels", []):
        all_links.extend(panel.get("links", []))
    link_text = json.dumps(all_links)
    markdown_text = "\n".join(
        panel.get("options", {}).get("content", "")
        for panel in dashboard.get("panels", [])
        if panel.get("type") == "text"
    )
    for title, uid in detail_contracts.items():
        if f"/d/{uid}/" not in link_text + markdown_text or title not in link_text + markdown_text:
            raise AssertionError(f"Missing validated link to {title} ({uid})")

    for panel_title, contract in STREAMS.items():
        panel = panel_by_title(dashboard, panel_title)
        if panel.get("datasource", {}).get("uid") != loki_uid:
            raise AssertionError(f"{panel_title} does not use provisioned datasource UID {loki_uid}")
        targets = panel.get("targets", [])
        if len(targets) != 1:
            raise AssertionError(f"{panel_title} must have exactly one focused query")
        target = targets[0]
        if target.get("datasource", {}).get("uid") != loki_uid:
            raise AssertionError(f"{panel_title} target datasource drifted")
        expression = str(target.get("expr", ""))
        constants = string_constants(ROOT / str(contract["module"]))
        service = constants[str(contract["service"])]
        event = constants[str(contract["event"])]
        states = [constants[name] for name in contract["states"]]
        if f'service_name="{service}"' not in expression or f'event_name="{event}"' not in expression:
            raise AssertionError(f"{panel_title} does not reference its shipped derived stream")
        if "[${lookback}]" not in expression:
            raise AssertionError(f"{panel_title} does not use the shared lookback variable")
        if f"sum by ({', '.join(contract['grouping'])})" not in expression:
            raise AssertionError(f"{panel_title} grouping does not match the shipped diagnostic grain")
        state_match = re.search(r'state=~"([A-Z_|]+)"', expression)
        referenced_states = set(state_match.group(1).split("|")) if state_match else set()
        if referenced_states != set(states):
            raise AssertionError(
                f"{panel_title} state query drifted: expected {sorted(states)}, got {sorted(referenced_states)}"
            )
        lowered = expression.lower()
        for unsafe in UNSAFE_QUERY_FIELDS:
            if unsafe in lowered:
                raise AssertionError(f"Unsafe field {unsafe!r} appears in {panel_title} query")
        if "codex_" in expression or "resourceMetrics" in expression:
            raise AssertionError(f"Native metric reference appears in {panel_title} query")

    boundaries = panel_by_title(dashboard, "Known boundaries").get("options", {}).get("content", "")
    for required in ("derived records only", "Silence or zero counts do not prove health", "not onboarding", "not proof"):
        if required not in boundaries:
            raise AssertionError(f"Known boundaries panel is missing: {required}")
    needs_attention = panel_by_title(dashboard, "Needs attention now").get("options", {}).get("content", "")
    if "default is **6h**" not in needs_attention or "selected lookback" not in needs_attention:
        raise AssertionError("Needs-attention panel does not document the shared lookback")

    documentation = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in FOCUSED_DOCS)
    for required in (
        "Codex Diagnostic Command Center",
        "existing privacy-safe derived",
        "not onboarding",
        "not production monitoring",
    ):
        if required.lower() not in documentation.lower():
            raise AssertionError(f"Focused docs are missing the Command Center boundary: {required}")
    unsafe_value_pattern = re.compile(
        r"(?i)(conversation_id|call_id|user_email|user_account_id|api_key)\s*[=:]\s*[\"'][^\"']+[\"']"
    )
    if unsafe_value_pattern.search(documentation):
        raise AssertionError("Focused docs contain an unsafe identifier or secret value")

    print(
        "Validated Command Center: "
        f"datasource={loki_uid}, streams={len(STREAMS)}, links={len(detail_contracts)}, lookback=6h"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
