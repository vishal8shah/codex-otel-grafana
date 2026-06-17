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

These dashboards use the labels emitted by Codex CLI/Desktop on this machine:
`service_name="Codex Desktop"` in Loki, `service="Codex Desktop"` in Prometheus
spanmetrics, and `resource.service.name = "Codex Desktop"` in Tempo TraceQL.

To recreate or refresh the dashboards:

```powershell
.\observability\setup-codex-dashboards.ps1
```

The Prometheus dashboard uses collector ingress metrics and Tempo-generated
spanmetrics. Codex `0.139.0` sends OTLP metric points, but this local LGTM stack
does not currently expose separate `codex_*` application metric names in
Prometheus.

The token economics dashboard uses Loki completion records and includes estimated
USD panels for total cost, input cost, output cost, cache savings, and cost
trend. The default pricing assumptions in `setup-codex-dashboards.ps1` are
input `$5.00/M`, cached input `$0.50/M`, and output `$30.00/M`; recheck official
pricing before budgeting.

```logql
{service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed"
```

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

Use `-Pull` the first time or whenever you want to refresh `grafana/otel-lgtm:latest`.
The start script mounts `observability\otelcol-config.yaml` when it exists.

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

This does not delete older records already stored in the Docker volume. To purge
all prior local observability data, stop and remove the container, remove the
`codex-otel-lgtm-data` Docker volume, start the stack again, and rerun
`setup-codex-dashboards.ps1`.

## Verify

```powershell
docker --version
docker ps --filter "name=codex-otel-lgtm"
Test-NetConnection localhost -Port 3000
Test-NetConnection localhost -Port 4317
Test-NetConnection localhost -Port 4318
Invoke-WebRequest http://localhost:3000 -UseBasicParsing
```

Then run a small Codex CLI command to emit telemetry:

```powershell
codex exec "Say only: otel smoke test"
```

Open Grafana at http://localhost:3000 and use Explore to check:

- Loki: `{service_name="Codex Desktop"}`
- Tempo: `{ resource.service.name = "Codex Desktop" }`
- Prometheus: `traces_spanmetrics_calls_total{service="Codex Desktop"}`
