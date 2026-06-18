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

## 4. Observed Logs

The following was observed in the existing local LGTM data on 2026-06-18. The
inspection queried structured metadata and field names only; example values
below are deliberately non-sensitive.

| Signal | Source | Status | Example field/value | Safe for dashboard? | Notes |
|---|---|---|---|---|---|
| Completion event | Loki log | Observed locally | `event_name=codex.sse_event`, `event_kind=response.completed` | Yes | Primary token record selector. |
| Token counts | Completion log | Observed locally | `input_token_count`, `output_token_count`, `cached_token_count`, `reasoning_token_count`, `tool_token_count` | Yes, aggregate only | Expected in logs, not Prometheus metrics unless later verified. |
| Model | Completion log | Observed locally | `model=<model-id>` | Yes, with cardinality review | Do not infer pricing from the model name alone. |
| Duration | Codex log metadata | Observed locally | `duration_ms=<number>` | Yes, after event scoping | Meaning depends on the associated event. |
| HTTP result | Codex log metadata | Observed locally | `http_response_status_code=<code>`, `success=<boolean>` | Yes | Scope to a verified event before interpreting. |
| Conversation identifier | Codex log metadata | Observed locally | `conversation_id=<identifier>` | No, raw value | Hash before grouping or export. |
| Prompt and identity fields | Historical local data | Observed locally; unsafe by default | `prompt`, `user_email`, `user_account_id` | No | Their historical presence proves the need for redaction. Current config must keep `log_user_prompt=false`; old retained data may predate redaction. |
| `codex.tool_decision` | Loki log | Not tested | `event_name=codex.tool_decision` | Only after observation | Run an interactive tool-use test. |
| `codex.tool_result` | Loki log | Not tested | `event_name=codex.tool_result` | Only after observation | Run an interactive tool-use test. |

## 5. Observed Metrics

No native Codex metric name is promoted to **Observed locally** in this Phase 0
ledger. Existing collector and span-derived metrics prove pipeline health, not
native Codex metric emission. Full verification must use interactive `codex`.

| Signal | Source | Status | Example field/value | Safe for dashboard? | Notes |
|---|---|---|---|---|---|
| `codex.conversation_starts` | Native Codex metric | Documented by official Codex docs; Not tested locally | Metric name only | No, until observed | Prometheus may normalize dots to underscores. Discover the actual stored name. |
| `codex.api_request` | Native Codex metric | Documented by official Codex docs; Not tested locally | Metric name only | No, until observed | Validate labels and unit interactively. |
| `codex.tool.call` | Native Codex metric | Documented by official Codex docs; Not tested locally | Metric name only | No, until observed | Do not equate with `codex mcp-server`. |
| `codex.tool.call.duration_ms` | Native Codex histogram | Documented by official Codex docs; Not tested locally | Metric name only | No, until observed | Confirm buckets, unit, and labels. |
| `traces_spanmetrics_*` | Collector-derived metric | Derived signal | Calls and latency from spans | Yes, marked derived | Not evidence that Codex emitted native metrics. |
| `otelcol_receiver_*` | Collector self-metric | Derived/setup health | Accepted records/points | Yes, health only | Cannot prove semantic correctness of Codex data. |

## 6. Observed Traces

Traces from the Codex service were previously visible through the local Tempo
pipeline, but Phase 0 has not captured a sanitized span-name and attribute
inventory suitable for this ledger. Trace availability is therefore recorded
as **Observed locally**, while individual span names and attributes remain
**Not tested**. Future verification must record only non-sensitive schema.

| Signal | Source | Status | Example field/value | Safe for dashboard? | Notes |
|---|---|---|---|---|---|
| Codex trace records | Tempo | Observed locally | `resource.service.name=Codex Desktop` | Yes | Reconfirm with an interactive session. |
| Individual span names | Tempo | Not tested | `<span-name>` | No, until observed | Do not infer from spanmetrics names alone. |
| Span duration/status | Tempo | Not tested | OTel duration/status | Only after observation | Standard OTel structure does not establish Codex semantics. |

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
4. Raw prompts, assistant messages, input messages, API keys, account IDs,
   emails, full paths, project/client names, and raw identifiers are ineligible.
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
- [ ] Record unknowns as **Not tested**, not **Not observed**.
- [ ] Review and accept this ledger before building advanced dashboards.

## 11. What Must Not Be Inferred

- Do not infer native metric emission from collector self-metrics or spanmetrics.
- Do not infer a field exists locally because official docs mention it.
- Do not infer a field is absent from a `codex exec` metrics test.
- Do not infer `codex mcp-server` activity from Codex client tool/MCP signals.
- Do not infer end-to-end turn latency from an unscoped `duration_ms` field.
- Do not infer exact cost without verified token semantics and current pricing.
- Do not infer "stuck" from silence alone until a heartbeat/state model exists.
- Do not infer that hashing makes low-entropy private values anonymous.
