# Codex Tool Failure Diagnosis

This companion analyzer answers one focused question: when a Codex run involves
a tool, was a result observed and did the schema-confirmed success field report
success or failure?

It queries raw codex.tool_decision and codex.tool_result logs from Loki,
immediately hashes the source conversation identifier, groups by run_hash and
tool_name, and can emit clearly derived codex.tool_diagnostic logs through the
local OTLP logs receiver.

## Confirmed fields used

- codex.tool_decision
- codex.tool_result
- tool_name
- success on tool results
- duration_ms on tool results
- source timestamps
- raw conversation identifier only as the input to a one-way hash

Raw call identifiers, arguments, output, paths, prompts, identity fields, model,
and provider are not copied or joined. Model/provider are not confirmed as a
safe same-record correlation for these tool logs.

The diagnostic groups by privacy-safe run_hash + tool_name. Raw call_id is an
unsafe identifier, so it is deliberately not exported or used in derived
records. The result is tool/run-level evidence, not individual-call proof.

## Run

    .\scripts\tool-failure.ps1
    .\scripts\tool-failure.ps1 -EmitDerived
    ./scripts/tool-failure.sh
    ./scripts/tool-failure.sh --emit-derived

Direct Python usage supports --window-minutes, --env-filter, --service-name,
--output-json, and --loki-limit.

Set CODEX_TOOL_DIAG_HASH_KEY to a stable private value to use HMAC-SHA256.
Without it, the analyzer warns and uses plain SHA-256.

## State model

- FAILED_RESULT: at least one observed result reported success=false.
- SUCCESSFUL_RESULT: every observed result reported success=true.
- SELECTED_NO_RESULT: a decision was observed for the tool/run pair but no
  result was observed in the selected window.
- UNKNOWN_RESULT: tool activity exists, but result evidence is incomplete.

SELECTED_NO_RESULT means no result was observed for that tool/run aggregate in
the selected window. It is suspicious evidence, not proof that a specific tool
call failed to dispatch or failed to return. Truncated or narrowly filtered
queries can also omit a result.

## Minimal validation trigger

The trigger emits exactly one fake failed-tool scenario using only
schema-confirmed raw log fields:

    python tools/tool-failure/synthetic_trigger.py
    python tools/tool-failure/tool_failure.py --emit-derived \
      --env-filter synthetic-tool-failure-phase3

The trigger sends a raw tool decision and tool result through OTLP /v1/logs. It
does not emit derived rows or metrics.

## Playbook

- **Symptom:** Codex selected a tool but the workflow failed, stalled, or
  produced no useful result.
- **Panel:** **Codex Tool Failure Diagnosis**.
- **Meaning:** a privacy-safe derived record shows tool-related activity with a
  failed, incomplete, or suspicious result pattern, based only on
  schema-confirmed telemetry.
- **Next action:** inspect tool_name, result state, source window,
  latest_duration_ms, and surrounding raw telemetry. Check MCP/server setup,
  tool availability, permissions, and local command/runtime assumptions. Treat
  the diagnostic as evidence for investigation, not proof of a Codex bug.

## Privacy and scope

Raw identifiers are hashed and discarded. Loki log bodies are ignored, and
source labels are reduced to an allowlist before aggregation. Derived rows never
contain prompts, identities, raw conversation or call identifiers, local paths,
tool arguments, or tool output.

The analyzer emits OTLP logs only. It does not emit or register native Codex
Prometheus metrics, read Tempo, diagnose APIs, analyze slow turns, or create a
broad tool reliability suite.

Repeated analyzer emissions can create repeated snapshot rows in the dashboard
table and log panel. Stat panels count unique run_hash + tool_name pairs or
unique tool names over the selected range, so repeated snapshots do not inflate
those counts.
