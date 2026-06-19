# Codex Diagnostic Kit

This repository provides a local-first diagnostic kit for OpenAI Codex on
Windows, macOS, and Linux using Docker and `grafana/otel-lgtm`.

## Positioning

This project is local-first, privacy-first, and issue-led. It targets real
classes of developer pain, but only ships diagnostics built from
schema-confirmed fields and a reviewed privacy boundary.

It is an evidence kit, not a claim that every useful Codex signal already
exists. Field eligibility and known entrypoint limitations are tracked in
[SCHEMA.md](SCHEMA.md). **Do not use `codex exec` to validate OTel metrics. Use
interactive `codex` for full schema discovery.**

It captures the setup we verified locally:

- Codex `0.139.0`
- Windows 10
- Docker Desktop with WSL2
- `grafana/otel-lgtm`
- Grafana, Loki, Tempo, Prometheus/Mimir-compatible metrics, and the
  OpenTelemetry Collector
- Codex user-level telemetry config in `%USERPROFILE%\.codex\config.toml`

## What You Get

- Grafana: http://localhost:3000
- OTLP/HTTP receiver: http://localhost:4318
- OTLP/gRPC receiver: localhost:4317
- Local dashboards for logs, traces, Prometheus spanmetrics, and token economics
- Collector-side redaction for user identity and prompt-like attributes
- Cross-platform start/stop and Grafana file-based dashboard provisioning
- A proven Codex Stuck Triage panel and playbook backed by privacy-safe
  `run_hash` values
- A focused Tool Failure Diagnosis panel and playbook using confirmed tool logs

## Dashboards

After setup, open Grafana with `admin` / `admin`:

- [Codex / Loki Logs](http://localhost:3000/d/codex-loki-logs/codex-loki-logs)
- [Codex / Tempo Traces](http://localhost:3000/d/codex-tempo-traces/codex-tempo-traces)
- [Codex / Prometheus Metrics](http://localhost:3000/d/codex-prometheus-metrics/codex-prometheus-metrics)
- [Codex / Token Economics](http://localhost:3000/d/codex-token-economics/codex-token-economics)
- [Codex Stuck Triage](http://localhost:3000/d/codex-stuck-burn-triage/codex-stuck-burn-triage)
- [Codex Tool Failure Diagnosis](http://localhost:3000/d/codex-tool-failure-diagnosis/codex-tool-failure-diagnosis)

## Capability Matrix

| Pain class | Status | Public claim |
|---|---|---|
| Codex goes quiet / appears stuck | **Shipped** | Codex Stuck Triage uses confirmed raw telemetry and privacy-safe `run_hash`. |
| MCP/tool startup hangs and failed results | **Shipped** | Tool Failure Diagnosis uses confirmed tool decision/result logs. |
| Tool dispatch uncertainty | **Partial** | Window-bounded selected-without-result evidence ships inside Tool Failure Diagnosis; broad dispatch proof is not claimed. |
| Review/resume flow stalls | **Acknowledged** | No claim until required signals are confirmed in `SCHEMA.md`. |
| API/backend reliability | **Backlog** | Request evidence exists; a reliability diagnostic has not shipped. |
| Token/cost ambiguity | **Partial / not claimed for burn** | Completed-run economics is distinct from token burn without completion. |

Token burn without completion was removed from Phase 2 because the required raw
telemetry shape was not schema-backed. No native `codex_*` metrics are claimed.

## Codex Stuck Triage

This focused derived analysis asks whether a run is still making progress or is
a stuck candidate. It is not native Codex telemetry and emits no native
`codex_*` metrics.

The analyzer hashes the observed raw run identifier immediately and exposes
only `run_hash`; raw identifiers are never written to output or Grafana.
`STUCK_CANDIDATE` is a threshold-based heuristic, not proof.

```text
.\scripts\run-health.ps1
.\scripts\run-health.ps1 -EmitDerived
./scripts/run-health.sh
./scripts/run-health.sh --emit-derived
```

Tune the six-hour window and two-/ten-minute thresholds with
`--window-minutes`, `--alive-threshold-seconds`, and
`--stuck-threshold-seconds`. See [the analyzer guide](tools/run-health/README.md)
for privacy, output and troubleshooting details.

### Shipped Playbook

- **Symptom:** Codex appears quiet, incomplete, or possibly stuck.
- **Panel:** **Codex Stuck Triage**.
- **Meaning:** a privacy-safe derived record shows a run with no completion and
  quiet time beyond the stuck threshold, based on confirmed raw telemetry.
- **Next action:** inspect `run_hash`, `state`, `quiet_for_seconds`,
  `last_event`, `model`, and the source time window. Treat it as a stuck
  candidate, not proof of a Codex bug.

`run_hash` is a privacy-safe hash of the source run identifier; the raw value is
never shown. Derived `codex.run_health` records are not native Codex telemetry,
and this feature emits no native `codex_*` metrics. Dashboard stats count unique
`run_hash` values in the selected range, while the table shows derived snapshots
and can contain repeated analyzer emissions for the same run.

## Codex Tool Failure Diagnosis

This focused companion analyzer groups schema-confirmed `codex.tool_decision`
and `codex.tool_result` logs by privacy-safe `run_hash` plus `tool_name`. It
classifies failed results, successful results, decisions with no observed result
in the selected window, and result activity with unknown success evidence.

```text
.\scripts\tool-failure.ps1
.\scripts\tool-failure.ps1 -EmitDerived
./scripts/tool-failure.sh
./scripts/tool-failure.sh --emit-derived
```

### Tool Failure Playbook

- **Symptom:** Codex selected a tool but the workflow failed, stalled, or
  produced no useful result.
- **Panel:** **Codex Tool Failure Diagnosis**.
- **Meaning:** a privacy-safe derived record shows tool-related activity with a
  failed, incomplete, or suspicious result pattern, based only on
  schema-confirmed telemetry.
- **Next action:** inspect `tool_name`, result state, timing/window, and
  surrounding raw telemetry. Check MCP/server setup, tool availability,
  permissions, and local command/runtime assumptions. Treat the diagnostic as
  evidence for investigation, not proof of a Codex bug.

Raw call IDs, arguments, output, prompts, identities, and local paths are never
emitted. Model/provider are omitted because a safe same-record correlation is
not confirmed for these tool logs. See
[the analyzer guide](tools/tool-failure/README.md).

## Quick Start

Copy `.env.example` to `.env` only if you need to change the safe local
defaults. The Compose configuration publishes Grafana and both OTLP receivers
on `127.0.0.1`; do not change these bindings to a public interface without
adding appropriate security controls.

### Windows PowerShell

```powershell
.\scripts\start.ps1 -Pull
.\scripts\doctor.ps1
.\scripts\schema-verify.ps1
.\scripts\run-health.ps1
codex
```

The existing `observability\start-lgtm.ps1` workflow remains available for
Windows users who need the original direct `docker run` path.

### macOS or Linux

```bash
./scripts/start.sh --pull
./scripts/doctor.sh
./scripts/schema-verify.sh
./scripts/run-health.sh
codex
```

Start, stop, datasource provisioning, and dashboard provisioning are
cross-platform. Docker Compose mounts the repository-owned Grafana provisioning
files and dashboards read-only, so macOS and Linux do not need `pwsh` for the
normal setup path.

### Docker Compose directly

```text
docker compose config
docker compose up -d
docker compose ps
```

Emit derived Stuck Triage rows with `scripts/run-health.ps1 -EmitDerived` or
`scripts/run-health.sh --emit-derived`. Stop the stack with
`scripts/stop.ps1`, `scripts/stop.sh`, or
`docker compose stop`. Pass `-Remove` or `--remove` to the wrapper scripts to
remove the container and Compose network while preserving the named data
volume. `LGTM_DATA_VOLUME` can select a separately named disposable volume for
isolated provisioning tests; never point a purge test at the retained default.
The default image is pinned to the runtime-tested
`grafana/otel-lgtm:0.28.0` tag (digest
`sha256:10f48eb2f8670134df542177bb19536c55421b089e43f9dfc2a27d4c078204d8`).
To update it, change `LGTM_IMAGE` in `.env.example` and the Compose fallback,
pull the candidate tag, then repeat retained-volume, clean-volume, Windows, and
WSL2 provisioning validation before merging. Roll back by restoring the prior
tag; do not use `latest` as a release default.

`observability/setup-codex-dashboards.ps1` remains available as a legacy manual
refresh and parity-comparison tool, but it is not required for normal
cross-platform provisioning.

Submit a tiny non-sensitive prompt in the interactive session, exit cleanly,
then verify the data in Grafana Explore. The schema verifier prints query hints.

**Validation warning:** do not use `codex exec` to validate metrics. Phase 0b
tested native `codex_*` Prometheus metrics with interactive Codex but did not
observe them in this stack. Unless later evidence establishes those metrics,
dashboards should rely on observed Loki logs and Tempo traces.

```logql
{service_name="Codex Desktop"}
```

```traceql
{ resource.service.name = "Codex Desktop" }
```

```promql
traces_spanmetrics_calls_total{service="Codex Desktop"}
```

## Correct Codex OTel Config

Codex telemetry routing must live in the user-level config file, not a
project-local `.codex/config.toml`:

```text
%USERPROFILE%\.codex\config.toml
```

Use this `[otel]` shape:

```toml
[otel]
environment = "local"
log_user_prompt = false
exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/logs", protocol = "binary" } }
trace_exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/traces", protocol = "binary" } }
metrics_exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/metrics", protocol = "binary" } }
```

The important detail is the inline exporter table. A plain
`exporter = "otlp-http"` value does not include the local endpoint metadata.

## Documentation

GitHub Pages-ready documentation lives under `docs/`:

- [Documentation Home](docs/index.html)
- [Manual Rebuild Guide](docs/rebuild-guide.html)
- [Architecture and Operations](docs/architecture-and-operations.html)
- [Diagnostic Capability Status](docs/builder-metrics.html)
- [Publishing to GitHub Pages](docs/publishing.html)

Phase sequencing and the schema acceptance gate are documented in
[PHASES.md](PHASES.md).

Future issue-led scenarios must reference verified issues, use the support
labels `Direct`, `Partial`, `Adjacent`, or `Not observable`, and avoid claiming
that this kit fixes Codex product bugs. Benefits should be phrased as helping to
diagnose, detect, explain, reproduce, or gather evidence.

## Source References

- OpenAI Codex OpenTelemetry docs:
  https://developers.openai.com/codex/config-advanced#open-telemetry
- OpenAI Codex config reference:
  https://developers.openai.com/codex/config-reference#otel
- OpenAI Codex local providers:
  https://developers.openai.com/codex/config-advanced#oss-mode-local-providers
- Grafana LGTM Docker image:
  https://github.com/grafana/docker-otel-lgtm

## Status

This is a local development and diagnostics setup. It is not a production
observability deployment. Do not expose Grafana or OTLP ports publicly without
authentication, TLS, network controls, and a reviewed retention/redaction policy.

For lightweight validation after setup, run `docker compose config`, the
platform doctor and schema verifier, and then inspect Loki and Tempo after one
small non-sensitive interactive Codex prompt.
