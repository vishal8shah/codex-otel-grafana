# Codex Observability Kit

This repository documents and automates a local observability stack for OpenAI
Codex on Windows using Docker Desktop and `grafana/otel-lgtm`.

## Positioning

This project is local-first, privacy-first, and issue-led. Hosted and
vendor-specific Codex OTel paths may exist; this repo focuses on local diagnosis
of token burn, slow runs, stuck sessions, tool/MCP failures, signal health, and
telemetry privacy.

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
- Reproducible PowerShell scripts for start, stop, and dashboard provisioning

## Dashboards

After setup, open Grafana with `admin` / `admin`:

- [Codex / Loki Logs](http://localhost:3000/d/codex-loki-logs/codex-loki-logs)
- [Codex / Tempo Traces](http://localhost:3000/d/codex-tempo-traces/codex-tempo-traces)
- [Codex / Prometheus Metrics](http://localhost:3000/d/codex-prometheus-metrics/codex-prometheus-metrics)
- [Codex / Token Economics](http://localhost:3000/d/codex-token-economics/codex-token-economics)

## Quick Start

```powershell
.\observability\start-lgtm.ps1 -Pull
.\observability\setup-codex-dashboards.ps1
.\scripts\doctor.ps1
.\scripts\schema-verify.ps1
codex
```

Submit a tiny non-sensitive prompt in the interactive session, exit cleanly,
then verify the data in Grafana Explore. The schema verifier prints query hints.

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
- [Builder Metrics and Token Economics](docs/builder-metrics.html)
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
