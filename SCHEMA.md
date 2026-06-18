# Codex OpenTelemetry Schema Ledger

## 1. Purpose

This file is the evidence gate for the Codex Observability Kit. It records what
Codex documents, what this repository has observed through the local OTLP
pipeline, and what remains unknown. A field appearing in documentation is not
proof that the installed Codex build emitted it.

Status vocabulary used here:

- **Documented by official Codex docs**: described by OpenAI, not necessarily
  emitted by the installed build or entrypoint.
- **Observed locally**: seen in the local Codex -> OTLP Collector -> LGTM path.
- **Not observed**: a valid discovery run checked for it and did not find it.
- **Not tested**: no valid discovery run has checked it.
- **Known unavailable**: the entrypoint is known not to emit the signal.
- **Derived signal**: computed from observed fields rather than emitted directly.
- **Requires helper script**: produced outside native Codex OTel.
- **Unsafe by default**: may expose sensitive content and must not be exported.

Official references:

- [Codex OpenTelemetry configuration](https://developers.openai.com/codex/config-advanced#open-telemetry)
- [Codex configuration reference](https://developers.openai.com/codex/config-reference#otel)
- [Codex notify configuration](https://developers.openai.com/codex/config-advanced#notify)

## 2. How Schema Discovery Should Be Performed

Full discovery requires an **interactive `codex` session**. Start the local
collector, run `scripts/schema-verify.ps1` or `scripts/schema-verify.sh`, launch
`codex`, submit a tiny non-sensitive prompt, exercise only the tool paths under
test, and exit cleanly so exporters can flush. Then inspect Loki, Prometheus,
and Tempo using the query hints printed by the verifier.

Record only field names, types, safe enum values, and aggregate counts. Never
paste raw log records into this file. A discovery result should include the
Codex version, entrypoint, date, platform, service name, and backend queried.

Schema verification is semi-manual. The scripts verify prerequisites and print
queries; they do not declare that a signal exists or is absent.

## 3. Known Entrypoint Limitations

- Interactive `codex` is the only accepted entrypoint for full OTel schema and
  metrics discovery.
- `codex exec` can emit logs and traces but is known not to emit OTel metrics.
  A metrics check performed with `codex exec` is **invalid** and must not be
  recorded as "not observed."
- `codex mcp-server` is currently **known unavailable** through Codex OTel. It
  must not be treated as an observable server process.
- Tool/MCP observability is limited to Codex acting as a client, and only when
  client-side calls appear in emitted logs, metrics, or traces.

## Fresh Interactive Discovery Run

This evidence was collected from a real interactive CLI session. Raw terminal
output and raw telemetry records were discarded; only schema keys, safe names,
counts, and safe enum-like values were retained locally in the gitignored
`schema-observation-output/` directory.

| Evidence item | Value |
|---|---|
| Date | 2026-06-18, 03:12:44-03:13:38 UTC |
| Codex version | `codex-cli 0.139.0` |
| Entrypoint | interactive `codex` (no subcommand) |
| Platform | Windows 10, Windows PowerShell 5.1 |
| Service name | `Codex Desktop` |
| Backend | local `grafana/otel-lgtm`: Loki, Prometheus, and Tempo through the Grafana HTTP proxy |
| Config path | user-level `%USERPROFILE%\.codex\config.toml` |
| Prompt logging | `log_user_prompt = false` |
| Logs exporter | `otlp-http` (`binary`) to `http://localhost:4318/v1/logs` |
| Metrics exporter | `otlp-http` (`binary`) to `http://localhost:4318/v1/metrics` |
| Trace exporter | `otlp-http` (`binary`) to `http://localhost:4318/v1/traces` |
| Data isolation | Retained historical data was present. The fresh run was isolated by `env=schema-tool-discovery-20260618-131244` and a bounded UTC query window. |
| Interaction | Non-sensitive smoke prompt plus one read-only `echo` shell tool call; the requested tool action did not read repository files |
| Exit | clean PTY EOF, process exit status `0`, followed by exporter flush time |
| Query method | sanitized Loki, Prometheus, and Tempo HTTP API queries; no raw records copied into this file |

The Loki selector used for the run was:

```logql
{service_name="Codex Desktop"} | env="schema-tool-discovery-20260618-131244"
```

The completion selector added:

```logql
| event_name="codex.sse_event" | event_kind="response.completed"
```

The run produced 46 structured log records. One completion, one tool decision,
and one tool result were observed. Tempo returned 31 traces carrying the unique
environment value. One trace in the bounded search window could not be fetched
because it exceeded Tempo's 5 MB query limit; its run attribution is unknown,
so the span inventory may be incomplete.

## 4. Observed Logs

Rows marked **Observed locally** below are supported by the fresh interactive
evidence stamp above. The isolation filter, rather than the retained volume as a
whole, is the source of evidence.

| Signal | Source | Status | Example field/value | Safe for dashboard? | Notes |
|---|---|---|---|---|---|
| `codex.conversation_starts` | Structured log event | Documented by official Codex docs; Observed locally | `event_name=codex.conversation_starts` | Yes, as a count | One event observed. It is not a native metric. |
| Completion event | Structured log event | Observed locally | `event_name=codex.sse_event`, `event_kind=response.completed` | Yes | One completion observed with the selector above. |
| Token counts | Completion log | Observed locally | `input_token_count`, `output_token_count`, `cached_token_count`, `reasoning_token_count`, `tool_token_count` | Yes, aggregate only | All five keys were present on the fresh completion record. Do not expose conversation-level values. |
| Model | Completion log | Observed locally | `model=<model-id>` | Yes, with cardinality review | Do not infer pricing from the model name alone. |
| API request result | `codex.api_request` log | Observed locally | `duration_ms`, `http_response_status_code`, `success`, `endpoint`, `attempt` | Yes, aggregate safe fields | One event observed. Endpoint values require a cardinality and privacy review. |
| Conversation identifier | Codex log metadata | Observed locally | `conversation_id=<identifier>` | No, raw value | Hash before grouping or export. |
| Prompt event | `codex.user_prompt` log | Observed locally | `prompt_length` | Aggregate only | One event observed. No `prompt` field was present with `log_user_prompt=false`. |
| Prompt and identity fields | Historical local data | Retained-data observation with unknown producer provenance; unsafe by default | `prompt`, `user_email`, `user_account_id` | No | Their historical presence proves the need for redaction, but they are not current-schema evidence. Current config must keep `log_user_prompt=false`. |
| `codex.tool_decision` | Structured log event | Observed locally | `decision`, `source`, `tool_name`, `call_id` | Aggregate safe fields only | One event observed. Raw call identifiers are ineligible. |
| `codex.tool_result` | Structured log event | Observed locally; unsafe fields present | `duration_ms`, `success`, `tool_name`, plus `arguments` and `output` keys | Aggregate safe fields only | One event observed. Never export raw tool arguments or output. |

The complete fresh event-name inventory also included `codex.startup_phase`,
`codex.turn_ttft`, `codex.websocket_connect`, `codex.websocket_event`, and
`codex.websocket_request`. These are observed log event names only; their
presence does not establish a same-named native metric.

No fresh log stream contained the keys `prompt`, `user_email`,
`user_account_id`, `input-messages`, `last-assistant-message`, `cwd`, or
`api_key`. This is a field-key check, not proof that every possible sensitive
value has been removed from free-form tool arguments or output.

Retained LGTM volumes can preserve telemetry that predates the current
redaction policy. Purge or reset that retained data before screenshots, public
demos, or sharing the local Grafana state if older records may contain prompt
or identity-like attributes.

## 5. Observed Metrics

The fresh interactive run queried Prometheus after a clean exporter flush. No
metric name matching `codex_*` was present. This supports **Not observed** only
for Codex CLI `0.139.0`, this interactive run, and this local pipeline. Existing
collector and span-derived metrics prove pipeline health, not native Codex
metric emission.

| Signal | Source | Status | Example field/value | Safe for dashboard? | Notes |
|---|---|---|---|---|---|
| `codex.api_request` | Native Codex metric | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | Checked using the valid interactive entrypoint. |
| `codex.api_request.duration_ms` | Native Codex metric | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | No normalized histogram or summary name was found. |
| `codex.sse_event` | Native Codex metric | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | The structured log event was observed; the native metric was not. |
| `codex.sse_event.duration_ms` | Native Codex metric | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | No normalized histogram or summary name was found. |
| `codex.websocket.request` | Native Codex metric | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | Checked using the valid interactive entrypoint. |
| `codex.websocket.request.duration_ms` | Native Codex metric | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | No normalized histogram or summary name was found. |
| `codex.websocket.event` | Native Codex metric | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | Checked using the valid interactive entrypoint. |
| `codex.websocket.event.duration_ms` | Native Codex metric | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | No normalized histogram or summary name was found. |
| `codex.tool.call` | Native Codex metric | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | Tool logs and spans were observed, but no native tool metric was found. |
| `codex.tool.call.duration_ms` | Native Codex histogram | Documented by official Codex docs; Not observed in fresh run | Metric name only | No | No normalized histogram or summary name was found. |
| `traces_spanmetrics_*` | Collector-derived metric | Derived signal | Calls and latency from spans | Yes, marked derived | Not evidence that Codex emitted native metrics. |
| `otelcol_receiver_*` | Collector self-metric | Derived/setup health | Accepted records/points | Yes, health only | Cannot prove semantic correctness of Codex data. |

## 6. Observed Traces

Tempo traces were isolated by the fresh run's exact `env` resource attribute.
Thirty-one traces matched; 56 unique span names, six resource attribute keys,
and 54 span attribute keys were collected without retaining trace IDs or values.
One oversized trace in the bounded window was skipped before environment
attribution, so this is a confirmed but potentially incomplete schema inventory.

| Signal | Source | Status | Example field/value | Safe for dashboard? | Notes |
|---|---|---|---|---|---|
| Codex trace records | Tempo | Observed locally | `resource.service.name=Codex Desktop`, resource `env=<isolated-run>` | Yes | 31 environment-matched traces were inspected. |
| Turn and tool span names | Tempo | Observed locally | `turn/start`, `shell_command`, `handle_tool_call`, `dispatch_tool_call_with_terminal_outcome` | Yes | Exact names observed in the isolated run. |
| Model transport span names | Tempo | Observed locally | `model_client.stream_responses_websocket`, `responses_websocket.stream_request`, `stream_request` | Yes | Exact names observed in the isolated run. |
| Resource attribute keys | Tempo | Observed locally | `env`, `service.name`, `service.version`, `telemetry.sdk.language`, `telemetry.sdk.name`, `telemetry.sdk.version` | Yes | Values other than safe service/environment identifiers were not retained. |
| Safe analytical span keys | Tempo | Observed locally | `tool_name`, `model`, `provider`, `http.method`, `rpc.method`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read.input_tokens`, `codex.usage.total_tokens` | Yes, with cardinality review | Exact keys observed; values were not copied into this ledger. |
| Sensitive span keys | Tempo | Observed locally; unsafe by default | `cwd`, `thread.id`, `thread.name`, `thread_id`, `turn.id`, `turn_id`, `call_id`, `submission.id`, `rpc.request_id`, `code.file.path` | No, raw values | Hash or drop before any dashboard grouping or export. |
| Span timing | Tempo | Observed locally | `startTimeUnixNano`, `endTimeUnixNano` | Yes, derived duration | No `status.code` value was observed in the inspected traces. |

## 7. Observed Notify Hook Payload Fields

No notify payload has been captured in a valid privacy-reviewed test, so no
notify field is marked locally observed. Official Codex notify examples describe
an `agent-turn-complete` payload with fields including `type`, `thread-id`,
`turn-id`, `cwd`, `input-messages`, and `last-assistant-message`. Treat these as
**Documented by official Codex docs / Not tested locally**.

`tools/notify-safe/notify_safe.py` accepts that payload but emits only timestamp,
event type, hashes of identifiers/path, and an explicitly opted-in project
basename. Raw input messages, assistant messages, prompts, cwd, and thread ID
are never emitted.

## 8. Confirmed vs Unconfirmed Richer Signals

| Signal | Source | Status | Example field/value | Safe for dashboard? | Notes |
|---|---|---|---|---|---|
| `turn.e2e_duration_ms` | Codex telemetry | Not tested | `<number>` | No, until observed | Do not substitute another duration field. |
| `mcp.call` | Codex client telemetry | Not tested | `<event-or-span>` | No, until observed | Server mode itself is known unavailable through OTel. |
| `approval.requested` | Codex telemetry | Not tested | `<event-or-span>` | No, until observed | Requires an interactive approval flow. |
| `task.compact` | Codex telemetry | Not tested | `<event-or-span>` | No, until observed | Requires an actual compaction flow. |
| Estimated token cost | Completion logs + price table | Derived signal | `tokens * configured rate` | Yes, marked estimate | Pricing is external, time-sensitive input. |
| Turn completion | Notify helper | Requires helper script | `event_type=agent-turn-complete` | Yes | Native OTel must not be implied. |
| Privacy-safe project group | Notify helper | Requires helper script | `cwd_hash=<sha256/hmac>` | Yes | Basename is opt-in and may leak a client/project name. |

## 9. Dashboard Field Eligibility Rules

1. Every panel must reference a field marked **Observed locally**, or label its
   input explicitly as **Derived signal**, **Requires helper script**, or sample.
2. Documentation alone does not make a field dashboard-eligible.
3. A result from `codex exec` cannot establish native metrics absence.
4. Raw prompts, assistant messages, input messages, tool arguments/output, API
   keys, account IDs, emails, full paths, project/client names, and raw
   identifiers are ineligible.
5. Derived cost panels must show their price assumptions and estimation status.
6. Collector self-metrics and spanmetrics must be labeled as pipeline/derived
   signals, not native Codex metrics.
7. High-cardinality labels require an explicit aggregation and retention review.

Future issue-led scenarios must use verified issue references and support labels
`Direct`, `Partial`, `Adjacent`, or `Not observable`. They may say the kit helps
diagnose, detect, explain, reproduce, or gather evidence; they must not claim it
fixes Codex product bugs. Do not seed `openai/codex#14593` without independent
verification.

Approved seeds for that future verification work are `openai/codex#5085`,
`#6172`, `#25132`, `#19607`, `#24618`, `#6664`, `#25061`, `#8481`, and
`#12913`. This list is not a support matrix and makes no observability claim.

## 10. Manual Verification Checklist

- [ ] Record Codex version, platform, date, entrypoint, and config location.
- [ ] Confirm `log_user_prompt = false` in the user-level config.
- [ ] Run `scripts/doctor.ps1` or `scripts/doctor.sh`.
- [ ] Run the matching schema verifier and read all entrypoint warnings.
- [ ] Launch interactive `codex`; do not use `codex exec` for metrics discovery.
- [ ] Submit a tiny prompt containing no private names or data.
- [ ] If testing tools, use a harmless local operation with no sensitive output.
- [ ] Exit cleanly and allow exporters time to flush.
- [ ] Query Loki for Codex event names and `response.completed` fields.
- [ ] Query Prometheus for actual native Codex metric names and labels.
- [ ] Query Tempo for sanitized span names and attribute keys.
- [ ] Confirm raw prompts, messages, emails, account IDs, and paths are absent.
- [ ] Purge or reset retained LGTM data that predates current redaction before screenshots, public demos, or sharing local Grafana state.
- [ ] Record unknowns as **Not tested**, not **Not observed**.
- [ ] Review and accept this ledger before building advanced dashboards.

## 11. What Must Not Be Inferred

- Do not infer native metric emission from collector self-metrics or spanmetrics.
- Do not generalize the native-metric non-observation beyond Codex CLI `0.139.0`
  and this valid interactive run.
- Do not infer a field exists locally because official docs mention it.
- Do not infer a field is absent from a `codex exec` metrics test.
- Do not infer `codex mcp-server` activity from Codex client tool/MCP signals.
- Do not infer end-to-end turn latency from an unscoped `duration_ms` field.
- Do not infer exact cost without verified token semantics and current pricing.
- Do not infer "stuck" from silence alone until a heartbeat/state model exists.
- Do not infer that hashing makes low-entropy private values anonymous.
- Do not treat the trace inventory as exhaustive; one oversized trace in the
  bounded window could not be fetched or attributed.
