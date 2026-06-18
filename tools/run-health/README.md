# Codex Stuck + Burn Triage Analyzer

This Python tool answers one narrow question: **is a Codex run still making
progress, or is it a stuck candidate while observed token usage accumulates?**

It queries local Codex logs through Grafana's Loki datasource proxy, groups
records by `run_hash`, classifies the current evidence, and can emit clearly
labelled `codex.run_health` derived logs back through the local OTLP logs
receiver. It does not emit native or Prometheus metrics.

## Requirements

- Python 3.10 or newer; no third-party packages are required.
- The local LGTM stack running at `http://localhost:3000`.
- Grafana credentials in `GRAFANA_USER` and `GRAFANA_PASSWORD` when they differ
  from the local `admin` / `admin` defaults.
- Prefer setting `CODEX_RUN_HEALTH_HASH_KEY` to a private, stable value. The
  tool uses HMAC-SHA256 when set and warns before falling back to plain SHA-256.

## Run

Dry run over the default six-hour window:

```text
python tools/run-health/run_health.py --dry-run
```

Use an isolated environment and tune thresholds:

```text
python tools/run-health/run_health.py --dry-run \
  --env-filter schema-tool-discovery-20260618-131244 \
  --window-minutes 360 \
  --alive-threshold-seconds 120 \
  --stuck-threshold-seconds 600
```

Write a safe local artifact under the gitignored output directory:

```text
python tools/run-health/run_health.py --dry-run \
  --output-json run-health-output/latest.json
```

Emit derived logs for the Grafana dashboard:

```text
python tools/run-health/run_health.py --emit-derived
```

## Minimal Validation Trigger

The validation trigger emits only four fake Codex-like source log records
through the real OTLP logs receiver: one stuck-candidate run and one
no-completion token-burn run. It does not emit `codex.run_health` rows or any
metrics. The analyzer must consume the source records and produce the derived
rows.

```text
python tools/run-health/synthetic_trigger.py --scenario stuck-candidate
python tools/run-health/synthetic_trigger.py --scenario no-completion-token-burn
python tools/run-health/run_health.py --emit-derived \
  --env-filter synthetic-stuck-burn-phase2
```

The trigger generates ephemeral fake identifiers in memory and never prints
them. It emits no prompts, identities, paths, tool arguments or tool output.
This is feature-validation support, not a generic telemetry generator.

Thin wrappers provide dry-run/explain mode by default and accept analyzer
arguments after the mode flag:

```text
.\scripts\run-health.ps1
.\scripts\run-health.ps1 -EmitDerived
./scripts/run-health.sh
./scripts/run-health.sh --emit-derived
```

The normal run uses the observed `Codex Desktop` service name. Override it with
`--service-name` or `CODEX_SERVICE_NAME` when the local Codex resource uses a
different safe service label.

## Output

Rows contain only:

- `run_hash`, state and safe timestamps
- age/quiet duration and completion status
- observed token counts
- safe event name and model
- event count, thresholds and explanatory notes

Raw identifiers, prompts, identities, paths, tool arguments and tool output are
never copied to output. Loki log bodies are ignored. Source stream metadata is
reduced to an allowlist and cleared after the raw identifier is hashed.

## State Model

- `COMPLETED_RECENTLY`: an observed `codex.sse_event` has
  `event_kind=response.completed` in the window.
- `SLOW_BUT_ALIVE`: no completion, but schema-confirmed activity is inside the
  alive threshold.
- `STUCK_CANDIDATE`: meaningful activity was observed, no completion was seen,
  and the run is quiet beyond the stuck threshold. This is a heuristic
  candidate, never proof.
- `NO_COMPLETION_TOKEN_BURN`: no completion, but actual schema-confirmed token
  fields were observed on records correlated to the same `run_hash`. Elapsed
  time alone can never produce this state.
- `UNKNOWN_INCOMPLETE`: evidence is insufficient for the other incomplete
  states.

`tokens_observed` is input plus output tokens. Cached and reasoning counts are
subsets, and `tool_token_count` semantics are not established strongly enough
in `SCHEMA.md` to add them without risking double counting.

## Privacy Model

`CODEX_RUN_HEALTH_HASH_KEY` enables stable HMAC-SHA256. If it is absent, plain
SHA-256 is used with a warning. Hashing reduces accidental identifier exposure;
it does not make low-entropy private values anonymous. Keep the HMAC key out of
the repository and use the same key when stable correlation is required.

The derived event is named `codex.run_health`, uses service name
`Codex Run Health`, and is labelled `source=derived` and
`derived_from=codex_logs`. It is not native Codex telemetry.

## Troubleshooting

- **Grafana connection failure:** run `scripts/start.ps1` or
  `scripts/start.sh`, wait for `/api/health`, then retry.
- **No rows:** expand `--window-minutes`, check the safe service name, and use an
  exact `--env-filter` only when that environment is present in retained data.
- **Truncation warning:** reduce the window or filter by environment. Do not
  classify a truncated result as comprehensive.
- **Dashboard empty:** run once with `--emit-derived`, allow the collector to
  flush, and query `{service_name="Codex Run Health"}` in Loki Explore.
- **401 from Grafana:** set `GRAFANA_USER` and `GRAFANA_PASSWORD`.

## Stuck + Burn Playbook

- **Symptom:** Codex seems stuck, silent, or expensive without a completed answer.
- **Check:** open **Grafana > Codex Stuck + Burn Triage**.
- **Meaning:** `STUCK_CANDIDATE` means meaningful activity went quiet beyond
  the threshold and is a heuristic, not proof; `NO_COMPLETION_TOKEN_BURN`
  means correlated token fields were observed without completion;
  `SLOW_BUT_ALIVE` has recent activity; `COMPLETED_RECENTLY` completed in the
  window; and `UNKNOWN_INCOMPLETE` lacks enough confirmed evidence.
- **Action:** inspect `run_hash`, `last_event`, `quiet_for_seconds`, and
  `tokens_observed`, then check safe Loki/Tempo context around the same
  `run_hash` and time window. Never pivot to or expose the raw identifier.

`run_hash` is a privacy-safe hash of the source run identifier; the raw value is
never shown. Derived `codex.run_health` records are not native Codex telemetry,
and no native `codex_*` metrics are used. An empty incomplete table is healthy
when **Runs analyzed** is non-zero and both problem stats are zero.

## Limitations

- The current implementation uses observed Codex logs only. It does not join
  Tempo usage because `SCHEMA.md` does not prove that trace thread identifiers
  equal the log run identifier.
- Silence alone is not proof of a stuck run; thresholds produce candidates.
- Token-burn classification requires actual correlated token fields and may be
  absent with the currently observed completion-only token shape.
- The analyzer is a manual snapshot tool, not a scheduler or broad run-health
  suite.
