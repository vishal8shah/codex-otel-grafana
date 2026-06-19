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
- Codex Stuck Triage: http://localhost:3000/d/codex-stuck-burn-triage/codex-stuck-burn-triage
- Codex Tool Failure Diagnosis: http://localhost:3000/d/codex-tool-failure-diagnosis/codex-tool-failure-diagnosis
- Codex API Request Reliability: http://localhost:3000/d/codex-api-request-reliability/codex-api-request-reliability
- Codex Slow Contributor Triage: http://localhost:3000/d/codex-slow-contributor-triage/codex-slow-contributor-triage

These dashboards use the labels emitted by Codex CLI/Desktop on this machine:
`service_name="Codex Desktop"` in Loki, `service="Codex Desktop"` in Prometheus
spanmetrics, and `resource.service.name = "Codex Desktop"` in Tempo TraceQL.

Docker Compose provisions the datasources and dashboards automatically from
the read-only files under `observability/provisioning/` and
`observability/dashboards/`.

It also provisions the focused `Codex stuck candidate detected` alert and its
local development webhook contact point. Grafana evaluates only derived
`codex.run_health` records; use `scripts/watch-stuck.ps1 -EmitDerived` or
`scripts/watch-stuck.sh --emit-derived` to keep those records fresh. The watcher
is opt-in and does not start with the stack. Start
`tools/alerting/dev_webhook_listener.py --host 0.0.0.0` before Docker runtime
proof. The listener itself defaults to `127.0.0.1`; the explicit wider bind is
needed only because Grafana reaches the host through `host.docker.internal`.
See its README for
the two-minute lookback, four-hour repeat interval, privacy boundary, and full
dependency chain.

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

## Codex Stuck Triage

The focused triage dashboard uses only `codex.run_health` derived logs from
`tools/run-health/run_health.py`. It shows unique analyzed runs, unique runs
with stuck-candidate records, and a privacy-safe incomplete-record table.

Raw run identifiers are hashed and dropped; Grafana receives `run_hash` only.
The stuck state is a heuristic candidate. No native `codex_*` metrics are created.

```text
python tools/run-health/run_health.py --dry-run
python tools/run-health/run_health.py --emit-derived
```

Use `--window-minutes`, `--alive-threshold-seconds`, and
`--stuck-threshold-seconds` to tune classification. The analyzer guide under
`tools/run-health/README.md` documents the complete privacy and state model.

### Stuck Playbook

- **Symptom:** Codex seems stuck or silent without a completed answer.
- **Check:** open **Grafana > Codex Stuck Triage**.
- **Meaning:** `STUCK_CANDIDATE` is a quiet-time heuristic, not proof;
  `SLOW_BUT_ALIVE` has recent activity; `COMPLETED_RECENTLY` completed in the
  window; and `UNKNOWN_INCOMPLETE` lacks enough confirmed evidence.
- **Action:** use `run_hash`, `last_event`, `quiet_for_seconds`, and
  time fields, then inspect safe Loki/Tempo context in the same time window
  without exposing the raw identifier.

`run_hash` is a privacy-safe hash of the source run identifier; the raw value is
never shown. The `codex.run_health` rows are derived rather than native Codex
telemetry, and no native `codex_*` metrics are used. Stats count unique
`run_hash` values in the selected range. The table is the primary evidence view
and can contain repeated derived snapshots when the analyzer runs more than once.

## Codex Tool Failure Diagnosis

The focused tool dashboard uses only derived `codex.tool_diagnostic` logs from
`tools/tool-failure/tool_failure.py`. It shows unique tool/run pairs, unique
tools with failed results, a privacy-safe triage table, and recent failures.

The analyzer reads confirmed `codex.tool_decision` and `codex.tool_result` logs,
hashes the raw source identifier into `run_hash`, and retains only `tool_name`,
confirmed result status/timing, safe counts, and source timestamps. Raw call
IDs, arguments, output, prompts, identities, and paths are discarded.

```text
python tools/tool-failure/tool_failure.py --dry-run
python tools/tool-failure/tool_failure.py --emit-derived
```

The dashboard is evidence for investigation. `SELECTED_NO_RESULT` is bounded by
the selected query window and means no result was observed for that
`run_hash + tool_name` aggregate. Raw `call_id` is deliberately excluded, so
this is tool/run-level evidence, not proof that a specific call failed to
dispatch or return. Repeated analyzer emissions may produce repeated snapshot
rows, while stat panels count unique tool/run pairs or unique tool names.

## Prerequisites

Install Docker Desktop if `docker --version` fails:

```powershell
winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements
```

Docker Desktop may require a Windows restart or first-run setup before the Docker CLI works.

## Codex API Request Reliability

This dashboard uses only derived `codex.api_diagnostic` logs from
`tools/api-reliability/api_reliability.py`. It provides three unique-group stats
and one privacy-safe triage table. Stats deduplicate repeated emissions by
`run_hash + endpoint_hash`; the table remains a snapshot view.

Raw endpoint and conversation values are hashed and dropped before derived
emission. Retained real endpoint values were unavailable for a defensible
low-cardinality mapping review, so `endpoint_hash` is used even though it is
less readable than a future `endpoint_kind`. Add `endpoint_kind` only after real
values are reviewed for cardinality and privacy; never expose raw endpoints by
default.

No per-request identifier is confirmed, so this is run/endpoint-level evidence
rather than proof about one request. A `FAILED_REQUEST` group may also contain
successful evidence from the same window; failure wins under the intentionally
conservative precedence. `RETRIED_REQUEST` and `SLOW_REQUEST` remain
group-level investigation evidence, not proof of a Codex service bug. The
configurable slow threshold is for local investigation, not an SLO.

```text
python tools/api-reliability/api_reliability.py --dry-run
python tools/api-reliability/api_reliability.py --emit-derived
```

The dashboard never uses or emits native `codex_*` metrics. See
`tools/api-reliability/README.md` for endpoint hashing, state semantics, and the
focused proof path.

## Codex Slow Contributor Triage

This dashboard uses derived `codex.slow_contributor` logs from
`tools/slow-contributor/slow_contributor.py`. It counts unique slow contributor
groups, unique API groups, and unique tool groups, then shows a privacy-safe
triage table. Repeated emissions add snapshots but do not inflate the stats.

The schema gate admits only `codex.api_request.duration_ms` grouped by
`run_hash + endpoint_hash` and `codex.tool_result.duration_ms` grouped by
`run_hash + tool_name`. TTFT payload fields, end-to-end turn duration, and
quiet/incomplete heuristics are excluded. The default 10,000 ms thresholds are
configurable local investigation aids, not SLOs.

```text
python tools/slow-contributor/slow_contributor.py --dry-run
python tools/slow-contributor/slow_contributor.py --emit-derived
```

This diagnostic identifies slow confirmed contributors in the selected window.
It does not measure full end-to-end Codex turn latency and does not prove a
Codex service bug. See `tools/slow-contributor/README.md` for the eligibility
table, privacy boundary, and proof path.

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
