# Codex OpenTelemetry + Grafana

This folder runs a local Grafana OpenTelemetry backend for Codex using the `grafana/otel-lgtm` Docker image.

## What It Provides

- Grafana: http://localhost:3000
- OTLP/HTTP: http://localhost:4318
- OTLP/gRPC: localhost:4317
- Login: `admin` / `admin`

The container includes Grafana, an OpenTelemetry Collector, Loki, Mimir, and Tempo. It is intended for local development and diagnostics, not production.

## Dashboards

The `Codex Observability` folder in Grafana contains:

- Codex / Loki Logs: http://localhost:3000/d/codex-loki-logs/codex-loki-logs
- Codex / Tempo Traces: http://localhost:3000/d/codex-tempo-traces/codex-tempo-traces
- Codex / Prometheus Metrics: http://localhost:3000/d/codex-prometheus-metrics/codex-prometheus-metrics
- Codex / Token Economics: http://localhost:3000/d/codex-token-economics/codex-token-economics
- Codex Stuck + Burn Triage: http://localhost:3000/d/codex-stuck-burn-triage/codex-stuck-burn-triage

These dashboards use the labels emitted by Codex CLI/Desktop on this machine:
`service_name="Codex Desktop"` in Loki, `service="Codex Desktop"` in Prometheus
spanmetrics, and `resource.service.name = "Codex Desktop"` in Tempo TraceQL.

Docker Compose provisions the datasources and dashboards automatically from
the read-only files under `observability/provisioning/` and
`observability/dashboards/`.

The PowerShell publisher remains as a legacy manual refresh for the direct-run
or other non-file-provisioned path, and as a parity comparison/export source:

```powershell
.\observability\setup-codex-dashboards.ps1
```

To regenerate dashboard JSON for an explicit parity review without publishing
through the API:

```powershell
.\observability\setup-codex-dashboards.ps1 `
  -ExportDirectory .\observability\dashboards `
  -ExportOnly
```

Review the resulting JSON diff before committing it; the exporter is not a
license to change panel or query behavior during provisioning maintenance.
Compose-managed dashboards deliberately reject API/UI overwrite so repository
JSON remains authoritative.

The Prometheus dashboard uses collector ingress metrics and Tempo-generated
spanmetrics. Phase 0b tested native `codex_*` Prometheus metrics with interactive
Codex `0.139.0`, but did not observe them in this local LGTM stack. Dashboards
should rely on the observed Loki logs and Tempo traces unless native metrics are
later observed.

The token economics dashboard uses Loki completion records and includes estimated
USD panels for total cost, input cost, output cost, cache savings, and cost
trend. The default pricing assumptions in `setup-codex-dashboards.ps1` are
input `$5.00/M`, cached input `$0.50/M`, and output `$30.00/M`; recheck official
pricing before budgeting.

```logql
{service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed"
```

## Codex Stuck + Burn Triage

The three-panel triage dashboard uses only `codex.run_health` derived logs from
`tools/run-health/run_health.py`. It shows stuck candidates, tokens actually
observed on incomplete runs, and a privacy-safe active/incomplete table.

Raw run identifiers are hashed and dropped; Grafana receives `run_hash` only.
The stuck state is a heuristic candidate, and no-completion token burn requires
correlated observed token fields. No native `codex_*` metrics are created.

```text
python tools/run-health/run_health.py --dry-run
python tools/run-health/run_health.py --emit-derived
```

Use `--window-minutes`, `--alive-threshold-seconds`, and
`--stuck-threshold-seconds` to tune classification. The analyzer guide under
`tools/run-health/README.md` documents the complete privacy and state model.

## Prerequisites

Install Docker Desktop if `docker --version` fails:

```powershell
winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements
```

Docker Desktop may require a Windows restart or first-run setup before the Docker CLI works.

## Start

```powershell
.\observability\start-lgtm.ps1 -Pull
```

The default image is pinned to the tested `grafana/otel-lgtm:0.28.0` tag. Use
`-Pull` after deliberately changing the tag. The Compose path mounts the
collector config, Grafana provisioning files, and dashboard JSON read-only.
The legacy direct-run script mounts only the collector config and does not
provide the normal file-provisioned dashboard path.

## Stop

```powershell
.\observability\stop-lgtm.ps1
```

To remove the stopped container while keeping the persisted `/data` Docker volume:

```powershell
.\observability\stop-lgtm.ps1 -Remove
```

## Codex Telemetry Config

Codex telemetry routing must live in the user-level config file:

```text
%USERPROFILE%\.codex\config.toml
```

Project-local `.codex\config.toml` files are not used for `otel` routing.

The local LGTM stack receives telemetry at:

- Logs: `http://localhost:4318/v1/logs`
- Traces: `http://localhost:4318/v1/traces`
- Metrics: `http://localhost:4318/v1/metrics`

Raw user prompt logging is disabled with `log_user_prompt = false`.

Use Codex's inline exporter table shape for OTLP endpoints. A plain
`exporter = "otlp-http"` value without endpoint metadata is not enough for this
local LGTM setup.

```toml
[otel]
environment = "local"
log_user_prompt = false
exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/logs", protocol = "binary" } }
trace_exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/traces", protocol = "binary" } }
metrics_exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/metrics", protocol = "binary" } }
```

## Local Redaction

`observability\otelcol-config.yaml` preserves LGTM's default signal routing and
adds an OpenTelemetry Collector transform processor before export. It drops
`user_email`, `user_account_id`, `user.email`, `user.account_id`, `user_prompt`,
and `prompt` attributes from logs, traces, and metrics before they reach Loki,
Tempo, or Prometheus.

This does not delete older records already stored in the Docker volume. Do not
remove `codex-otel-lgtm-data` during normal stop/remove or provisioning
validation. Purging retained telemetry is a separate, explicit operation.

## Image Update Process

The validated image is `grafana/otel-lgtm:0.28.0`, digest
`sha256:10f48eb2f8670134df542177bb19536c55421b089e43f9dfc2a27d4c078204d8`.
For an update, pin a candidate tag in `.env.example` and `docker-compose.yml`,
pull it explicitly, inspect its Grafana provisioning paths, and repeat the full
retained-volume and isolated clean-volume checks on Windows and WSL2. Restore
`0.28.0` to roll back. Do not replace the default with `latest`.

## Verify

```powershell
docker --version
docker ps --filter "name=codex-otel-lgtm"
Test-NetConnection localhost -Port 3000
Test-NetConnection localhost -Port 4317
Test-NetConnection localhost -Port 4318
Invoke-WebRequest http://localhost:3000 -UseBasicParsing
```

Then launch an interactive Codex CLI session and submit a small, non-sensitive
prompt to emit telemetry:

```powershell
codex
```

Do not use `codex exec` for metrics validation; Phase 0b's discovery evidence is
based on the interactive entrypoint.

Open Grafana at http://localhost:3000 and use Explore to check:

- Loki: `{service_name="Codex Desktop"}`
- Tempo: `{ resource.service.name = "Codex Desktop" }`
- Prometheus: `traces_spanmetrics_calls_total{service="Codex Desktop"}`
