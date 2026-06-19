# Codex API Request Reliability

This focused analyzer reads schema-confirmed `codex.api_request` logs from
local Loki and emits privacy-safe derived `codex.api_diagnostic` log records.
It does not emit native `codex_*` metrics.

## Evidence boundary

The analyzer reads only fields confirmed in `SCHEMA.md`: `duration_ms`,
`http_response_status_code`, `success`, `attempt`, `endpoint`, and the raw
`conversation_id` needed solely to derive a run hash. Source labels and log
bodies are discarded after the allowlisted fields are extracted.

Raw endpoint values are never exported. The analyzer uses
`run_hash + endpoint_hash` because there is no confirmed safe per-request ID
and retained real endpoint values were unavailable for a defensible
low-cardinality mapping review. When `CODEX_API_DIAG_HASH_KEY` is set, both
hashes use HMAC-SHA256. If it is unset, the analyzer warns before falling back
to plain SHA-256. Hashing low-entropy endpoint values is a privacy boundary,
not anonymization; use a private key for shared or retained environments.

The result is run/endpoint-level investigation evidence, not proof about an
individual request and not proof of a Codex service bug. Attempts are not
summed as failures. `max_attempt > 1` is retained as a group-level retry flag.
Repeated analyzer emissions may create repeated snapshot rows in the table;
stat panels count unique `run_hash + endpoint_hash` groups over the selected
range.

## State model

Precedence is deterministic across every API event in a run/endpoint group:

1. `FAILED_REQUEST`: `success=false` or a `4xx`/`5xx` status bucket was observed.
2. `RETRIED_REQUEST`: no failed evidence exists and `attempt > 1` was observed.
3. `SLOW_REQUEST`: no higher state exists and duration exceeded the configured threshold.
4. `SUCCESSFUL_REQUEST`: success or a `2xx` bucket exists with no higher state.
5. `UNKNOWN_REQUEST`: request evidence exists but outcome evidence is incomplete.

The default slow threshold is 10,000 ms and can be changed with
`--slow-threshold-ms`. It is a conservative local investigation threshold, not
a service-level objective or end-to-end latency measure. The derived
`slow_observed` flag remains true when a higher-priority failed or retried state
wins, allowing the slow-group stat to remain independently useful.

## Run

```powershell
$env:CODEX_API_DIAG_HASH_KEY = "use-a-private-local-secret"
.\scripts\api-reliability.ps1
.\scripts\api-reliability.ps1 -EmitDerived
```

```bash
export CODEX_API_DIAG_HASH_KEY="use-a-private-local-secret"
./scripts/api-reliability.sh
./scripts/api-reliability.sh --emit-derived
```

Useful options include `--window-minutes`, `--slow-threshold-ms`,
`--env-filter`, `--loki-limit`, and `--output-json`.

## Focused synthetic proof

When real failed/retried/slow telemetry is unavailable, run:

```powershell
python .\tools\api-reliability\synthetic_trigger.py --env synthetic-api-reliability-proof
$env:CODEX_API_DIAG_HASH_KEY = "proof-only-private-key"
.\scripts\api-reliability.ps1 -EmitDerived --env-filter synthetic-api-reliability-proof
```

The trigger emits two schema-shaped raw `codex.api_request` logs through OTLP
`/v1/logs`. It never emits `codex.api_diagnostic` directly and never emits
metrics. The analyzer must read those raw records, hash the run and endpoint,
classify the group, and emit the derived row used by Grafana.

## Playbook

- **Symptom:** Codex feels slow, unreliable, or fails around model/backend activity.
- **Panel:** **Codex API Request Reliability**.
- **Meaning:** a privacy-safe derived record shows failed, slow, retried, or
  incomplete API request evidence from schema-confirmed telemetry.
- **Next action:** inspect state, maximum duration, status bucket,
  retry/attempt evidence, endpoint hash, run hash, and source window. Treat the
  result as investigation evidence, not proof of a Codex service bug.
