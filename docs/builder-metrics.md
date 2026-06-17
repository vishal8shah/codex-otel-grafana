# Builder Metrics and Token Economics

This document answers the builder question: what would a Codex user actually
want to monitor?

## Metrics Builders Care About

### Reliability

- Request success/failure
- WebSocket/SSE event success
- Tool call success/failure
- Error and warning rate
- MCP startup and shutdown failures

Useful sources:

- Loki events: `codex.websocket_event`, `codex.sse_event`, `codex.tool_result`
- Tempo traces: failed or long spans
- Prometheus spanmetrics: calls by `status_code`

### Latency

- Time to first token
- API request duration
- WebSocket request duration
- Tool execution duration
- Startup phase duration
- Long-running MCP/tool phases

Useful sources:

- Loki fields: `duration_ms`, `event_name`, `startup_phase`
- Tempo spans: `turn/start`, `codex.exec`, `serve_inner`, tool spans
- Prometheus: `traces_spanmetrics_latency_bucket`

### Throughput

- Number of Codex runs
- Number of completions
- Number of tool calls
- Events per run
- Span rate by operation

Useful sources:

- Loki `count_over_time`
- Prometheus `traces_spanmetrics_calls_total`

### Token Economics

Token economics are usually the highest-interest builder metric because they
connect engineering behavior to cost, context design, latency, and model choice.

The verified Codex completion logs include:

- `input_token_count`
- `output_token_count`
- `cached_token_count`
- `reasoning_token_count`
- `tool_token_count`
- `model`
- `conversation_id`

Completion records are queried with:

```logql
{service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed"
```

Input token total:

```logql
sum(sum_over_time({service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed" | unwrap input_token_count [6h]))
```

Output token total:

```logql
sum(sum_over_time({service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed" | unwrap output_token_count [6h]))
```

Completion count:

```logql
sum(count_over_time({service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed" [6h]))
```

## Have We Built Token Economics Yet?

Yes, as a first local version.

The `Codex / Token Economics` dashboard now includes:

- Input tokens
- Output tokens
- Cached tokens
- Reasoning tokens
- Tool tokens
- Completion count
- Token trend by type
- Token mix
- Raw completion log records

What is not built yet:

- Dollar cost calculation by model price.
- Budget thresholds and alerts.
- Per-project or per-repository cost breakdown.
- Provider-normalized cost for local vs hosted models.
- Export to CSV or long-term accounting tables.

Those require a pricing table and a more deliberate cost model. The right
next step is to add a small configurable model pricing map instead of hardcoding
prices into dashboards.

## Suggested Dashboard Roadmap

### v1 Already Built

- Logs dashboard
- Traces dashboard
- Prometheus/spanmetrics dashboard
- Token economics dashboard
- Collector-side redaction
- Repeatable provisioning

### v2 Recommended

- Cost estimates by model and token class.
- Per-conversation token totals.
- Per-tool latency and failure leaderboard.
- Error budget style view for failed events.
- Run comparison across model/provider.
- Longest trace and slowest span tables.
- Prompt/cache efficiency: cached tokens divided by total input tokens.

### v3 Optional

- Alerts.
- GitHub Actions smoke test for dashboard JSON.
- Screenshot assets for documentation.
- Grafana provisioning files mounted at container start.
- Separate compose file for multi-container production-like topology.

## Do These Dashboards Work With Local Models?

Mostly yes, with an important caveat.

OpenAI's Codex docs say Codex can run against local open-source providers such
as Ollama or LM Studio when using `--oss`, and `oss_provider` can select the
default local provider.

Because telemetry is emitted by the Codex process, the logs, traces, collector
health, and spanmetrics dashboards should still work when Codex is run against a
local provider.

Token economics may vary:

- If the local provider returns token usage in a shape Codex records, the token
  dashboard should populate.
- If the local provider does not return OpenAI-style token usage, token fields
  may be missing or zero.
- Local models usually do not map cleanly to hosted API pricing, so dollar-cost
  panels should be optional and provider-specific.

Recommended local model smoke test:

```powershell
codex --oss exec "Say only: local otel smoke test"
```

Then check:

```logql
{service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed"
```

If token fields appear, token economics works for that local provider. If they
do not, the logs/traces dashboards still work, but cost/token panels need a
provider-specific enrichment path.
