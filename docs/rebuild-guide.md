# Manual Rebuild Guide

This guide lets another Windows user reproduce the full local Codex
OpenTelemetry and Grafana setup from scratch.

## Prerequisites

- Windows 10 or later
- PowerShell
- Docker Desktop with WSL2 backend
- Codex CLI installed and authenticated
- Local admin rights if Docker Desktop or WSL needs setup

Verify Codex:

```powershell
codex --version
codex doctor
```

Verify Docker:

```powershell
docker --version
docker info
```

If Docker is missing:

```powershell
winget install -e --id Docker.DockerDesktop --source winget --accept-source-agreements --accept-package-agreements
```

Docker Desktop may require WSL2, Ubuntu setup, first launch, or a reboot.

## Step 1: Start Grafana LGTM

From the repository root:

```powershell
.\observability\start-lgtm.ps1 -Pull
```

The script starts a container named `codex-otel-lgtm` with:

- Grafana on `http://localhost:3000`
- OTLP/gRPC on `localhost:4317`
- OTLP/HTTP on `http://localhost:4318`
- Persistent Docker volume `codex-otel-lgtm-data`
- A mounted collector config at `observability\otelcol-config.yaml`

Check the container:

```powershell
docker ps --filter "name=^/codex-otel-lgtm$"
```

Expected status: `healthy`.

## Step 2: Configure Codex Telemetry

Edit the user-level Codex config:

```text
%USERPROFILE%\.codex\config.toml
```

Add or update:

```toml
[otel]
environment = "local"
log_user_prompt = false
exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/logs", protocol = "binary" } }
trace_exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/traces", protocol = "binary" } }
metrics_exporter = { otlp-http = { endpoint = "http://localhost:4318/v1/metrics", protocol = "binary" } }
```

Important:

- Do this in `~\.codex\config.toml`, not project `.codex\config.toml`.
- Keep `log_user_prompt = false` unless you explicitly want raw prompts stored.
- Use inline exporter tables so the endpoints are attached to each exporter.

Validate:

```powershell
codex doctor
```

The config check should load successfully.

## Step 3: Provision Dashboards

Run:

```powershell
.\observability\setup-codex-dashboards.ps1
```

This creates or updates a Grafana folder named `Codex Observability` and these
dashboards:

- `Codex / Loki Logs`
- `Codex / Tempo Traces`
- `Codex / Prometheus Metrics`
- `Codex / Token Economics`

## Step 4: Generate Smoke Telemetry

Run:

```powershell
codex exec "Say only: otel smoke test"
```

This creates a short Codex run and should emit logs, traces, and metrics through
the local collector.

## Step 5: Verify Data

Open Grafana:

```text
http://localhost:3000
```

Login:

```text
admin / admin
```

Use Explore with these queries.

Loki:

```logql
{service_name="Codex Desktop"}
```

Tempo:

```traceql
{ resource.service.name = "Codex Desktop" }
```

Prometheus:

```promql
traces_spanmetrics_calls_total{service="Codex Desktop"}
```

Token completion records:

```logql
{service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed"
```

Token totals:

```logql
sum(sum_over_time({service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed" | unwrap input_token_count [6h]))
```

## Step 6: Stop or Recreate

Stop the container:

```powershell
.\observability\stop-lgtm.ps1
```

Remove the container but keep data:

```powershell
.\observability\stop-lgtm.ps1 -Remove
```

Purge all stored observability data:

```powershell
.\observability\stop-lgtm.ps1 -Remove
docker volume rm codex-otel-lgtm-data
.\observability\start-lgtm.ps1
.\observability\setup-codex-dashboards.ps1
```

## Common Problems

### Grafana Is Up But Dashboards Are Empty

Check the Codex config shape. The inline exporter tables must include endpoint
metadata. Then run a fresh `codex exec` smoke test.

### Loki Shows Logs But No Token Dashboard Data

Token counts appear on completion records only:

```logql
{service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed"
```

Short runs that fail before completion may not have token counts.

### Prometheus Has Collector Metrics But No `codex_*` Metrics

This is expected in the verified local LGTM setup. Codex sends metric points,
but the visible Prometheus surface currently exposes collector ingress metrics
and Tempo-generated spanmetrics. Use Loki for token economics and Tempo
spanmetrics for latency/throughput.

### Identity Attributes Show Up In Old Logs

The collector now drops identity attributes before export, but old records in
the Docker volume remain. Remove `codex-otel-lgtm-data` to purge old local data.
