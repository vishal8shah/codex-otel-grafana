# Codex Slow Contributor Triage

This focused analyzer identifies slow **confirmed contributors** in a selected
window. It is not an end-to-end turn-latency diagnostic and must not be used to
infer total Codex turn duration from unscoped `duration_ms` fields.

## Schema eligibility gate

| Candidate contributor | Source event/span | Confirmed fields | Safe grouping key | Eligible? | Reason |
|---|---|---|---|---|---|
| API request duration | `codex.api_request` log | `duration_ms`, `endpoint`, raw `conversation_id` for immediate hashing | `run_hash + endpoint_hash` | Yes | `SCHEMA.md` confirms the duration and grouping inputs; raw endpoint and run values are hashed and dropped. |
| Tool result duration | `codex.tool_result` log | `duration_ms`, `tool_name`, raw `conversation_id` for immediate hashing | `run_hash + tool_name` | Yes | `SCHEMA.md` confirms duration and tool name; raw call ID, arguments, and output are excluded. |
| TTFT | `codex.turn_ttft` log | Event name only in `SCHEMA.md` | None confirmed | No | Retained records showed a duration-shaped field and run correlation, but also unsafe identity fields. The accepted schema confirms only the event name, so payload use is blocked. |
| End-to-end turn duration | Unconfirmed `turn.e2e_duration_ms` | None | None | No | `SCHEMA.md` marks it untested and explicitly forbids substituting another duration. |
| Quiet/incomplete evidence | Derived `codex.run_health` | Privacy-safe run state and quiet-time evidence | `run_hash` | No for this diagnostic | Safe derived evidence exists, but it is a stuck/incomplete heuristic rather than a confirmed timing contributor. Reusing it here would blur the diagnostic claim. |

Only API and tool result durations pass. `codex.turn_ttft` remains an observed
event name, not a usable timing contributor. No TTFT state or panel is added.

## Privacy and grouping

The analyzer allowlists only event name, `duration_ms`, `tool_name`, endpoint,
and the raw run identifier needed solely for immediate hashing. API groups use
`run_hash + endpoint_hash`; tool groups use `run_hash + tool_name`. Set
`CODEX_SLOW_CONTRIBUTOR_HASH_KEY` to use HMAC-SHA256 for run and endpoint
hashes. The analyzer warns before plain SHA-256 fallback.

Raw prompts, identities, conversation identifiers, endpoints, call IDs, local
paths, tool arguments, and tool output are never emitted. The result is
contributor-level evidence, not exact turn-level proof.

## States and thresholds

- `SLOW_API_CONTRIBUTOR`: an API group exceeded its local threshold.
- `SLOW_TOOL_CONTRIBUTOR`: a tool group exceeded its local threshold.
- `MULTIPLE_SLOW_CONTRIBUTORS`: more than one slow contributor group was
  observed for the same privacy-safe run in the selected window.

Both defaults are 10,000 ms and are configurable with
`--api-slow-threshold-ms` and `--tool-slow-threshold-ms`. Thresholds are local
investigation aids, not SLOs. These states do not prove total turn latency or a
Codex service bug. Events below threshold do not produce derived rows.

Repeated analyzer runs may create repeated snapshot rows. Dashboard stats count
unique API groups by `run_hash + endpoint_hash` and unique tool groups by
`run_hash + tool_name` over the selected range.

## Run

```powershell
$env:CODEX_SLOW_CONTRIBUTOR_HASH_KEY = "use-a-private-local-secret"
.\scripts\slow-contributor.ps1
.\scripts\slow-contributor.ps1 -EmitDerived
```

```bash
export CODEX_SLOW_CONTRIBUTOR_HASH_KEY="use-a-private-local-secret"
./scripts/slow-contributor.sh
./scripts/slow-contributor.sh --emit-derived
```

## Focused synthetic proof

```powershell
python .\tools\slow-contributor\synthetic_trigger.py --env synthetic-slow-contributor-proof
$env:CODEX_SLOW_CONTRIBUTOR_HASH_KEY = "proof-only-private-key"
.\scripts\slow-contributor.ps1 -EmitDerived --env-filter synthetic-slow-contributor-proof
```

The trigger emits one slow API request and one slow tool result as raw,
schema-shaped logs through OTLP `/v1/logs`. It does not emit derived rows or
metrics. The analyzer must read the raw records from Loki and emit privacy-safe
`codex.slow_contributor` rows before Grafana can light up.

## Playbook

- **Symptom:** Codex feels slow or appears to spend too long between user
  request and useful response.
- **Panel:** **Codex Slow Contributor Triage**.
- **Meaning:** a privacy-safe derived record shows one or more slow confirmed
  contributors, currently API request duration or tool result duration. This
  does not measure full end-to-end turn latency.
- **Next action:** inspect contributor type, duration, threshold, run hash,
  endpoint hash or tool name, and source window. Treat it as investigation
  evidence, not proof of total turn latency or a Codex service bug.
