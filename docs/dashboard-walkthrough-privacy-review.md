# Dashboard Walkthrough Screenshot Privacy Review

Review date: 2026-06-20

Demo profile: `walkthrough-rich`

Capture method: actual file-provisioned Grafana dashboards running in the local
`grafana/otel-lgtm` stack. The reusable demo emitter sent schema-confirmed
synthetic source events through OTLP `/v1/logs`; Loki retained the raw evidence,
the shipped analyzers emitted privacy-safe derived records back through OTLP,
and the existing Grafana dashboards rendered those records. The stack previews
also use standard synthetic spans sent through OTLP `/v1/traces`, retained by
Tempo and converted to generated spanmetrics for Prometheus. Captures use
bounded source windows and Grafana kiosk mode, with no browser or operating-
system chrome.

Every image below was inspected at its original 1280×720 resolution. The
`Synthetic example data` label is rendered beside each image in
`docs/index.html`; the dashboard screenshot itself is a direct capture and was
not edited or annotated.

Automated validation checks references, alt text, nearby synthetic labels, one
review entry per image, PNG signature and dimensions, metadata chunks, and raw-
byte unsafe markers. Manual review covers visible pixels, rendered text,
privacy, and whether the image could overstate the dashboard capability.

## `docs/assets/dashboard-walkthrough/command-center.png`

- Dashboard captured: Codex Diagnostic Command Center
- Synthetic demo profile used: `walkthrough-rich`
- Proof path used: synthetic OTLP → Loki raw evidence → shipped analyzers → Loki derived records → Grafana
- Capture/review date: 2026-06-20
- Reviewer/check status: reviewed
- Manual pixel/content review: completed at original 1280×720 resolution
- Panel content: synthetic category counts and investigation guidance only; it surfaces and routes without ranking
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Alt text: contains `synthetic example data`
- Browser/OS chrome and tooltips: absent
- Prompts or prompt fragments: absent
- Real names, emails, usernames, accounts, tenants, hostnames, or organisations: absent
- Raw conversation, run, call, thread, or request IDs: absent
- Raw local paths or raw endpoints: absent
- Tool arguments or tool output: absent
- Keys, secrets, tokens, auth headers, or account IDs: absent
- Real model, provider, or account details: absent
- Misleading real-user or real-system data: absent
- Visual overclaim review: passed; the image shows synthetic investigation evidence, not a bug verdict or category priority

## `docs/assets/dashboard-walkthrough/stuck-triage.png`

- Dashboard captured: Codex Stuck Triage
- Synthetic demo profile used: `walkthrough-rich`
- Proof path used: synthetic OTLP → Loki raw evidence → shipped analyzers → Loki derived records → Grafana
- Capture/review date: 2026-06-20
- Reviewer/check status: reviewed
- Manual pixel/content review: completed at original 1280×720 resolution
- Panel content: privacy-safe run hashes, derived states, bounded timestamps/timing, completion flags, and safe event types only
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Alt text: contains `synthetic example data`
- Browser/OS chrome and tooltips: absent
- Prompts or prompt fragments: absent
- Real names, emails, usernames, accounts, tenants, hostnames, or organisations: absent
- Raw conversation, run, call, thread, or request IDs: absent
- Raw local paths or raw endpoints: absent
- Tool arguments or tool output: absent
- Keys, secrets, tokens, auth headers, or account IDs: absent
- Real model, provider, or account details: absent
- Misleading real-user or real-system data: absent
- Visual overclaim review: passed; candidate states remain investigation evidence and do not establish a bug verdict or system health

## `docs/assets/dashboard-walkthrough/tool-failure.png`

- Dashboard captured: Codex Tool Failure Diagnosis
- Synthetic demo profile used: `walkthrough-rich`
- Proof path used: synthetic OTLP → Loki raw evidence → shipped analyzers → Loki derived records → Grafana
- Capture/review date: 2026-06-20
- Reviewer/check status: reviewed
- Manual pixel/content review: completed at original 1280×720 resolution
- Panel content: synthetic tool names, aggregate result states, privacy-safe run hashes, bounded timestamps, and decision/result counts only
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Alt text: contains `synthetic example data`
- Browser/OS chrome and tooltips: absent
- Prompts or prompt fragments: absent
- Real names, emails, usernames, accounts, tenants, hostnames, or organisations: absent
- Raw conversation, run, call, thread, or request IDs: absent
- Raw local paths or raw endpoints: absent
- Tool arguments or tool output: absent
- Keys, secrets, tokens, auth headers, or account IDs: absent
- Real model, provider, or account details: absent
- Misleading real-user or real-system data: absent
- Visual overclaim review: passed; aggregates do not claim an individual tool-call failure or an identified root cause

## `docs/assets/dashboard-walkthrough/api-reliability.png`

- Dashboard captured: Codex API Request Reliability
- Synthetic demo profile used: `walkthrough-rich`
- Proof path used: synthetic OTLP → Loki raw evidence → shipped analyzers → Loki derived records → Grafana
- Capture/review date: 2026-06-20
- Reviewer/check status: reviewed
- Manual pixel/content review: completed at original 1280×720 resolution
- Panel content: derived states, status buckets, privacy-safe run/endpoint hashes, bounded timestamps, durations, and attempt evidence only
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Alt text: contains `synthetic example data`
- Browser/OS chrome and tooltips: absent
- Prompts or prompt fragments: absent
- Real names, emails, usernames, accounts, tenants, hostnames, or organisations: absent
- Raw conversation, run, call, thread, or request IDs: absent
- Raw local paths or raw endpoints: absent
- Tool arguments or tool output: absent
- Keys, secrets, tokens, auth headers, or account IDs: absent
- Real model, provider, or account details: absent
- Misleading real-user or real-system data: absent
- Visual overclaim review: passed; group-level evidence does not establish an individual request failure or service defect

## `docs/assets/dashboard-walkthrough/slow-contributor.png`

- Dashboard captured: Codex Slow Contributor Triage
- Synthetic demo profile used: `walkthrough-rich`
- Proof path used: synthetic OTLP → Loki raw evidence → shipped analyzers → Loki derived records → Grafana
- Capture/review date: 2026-06-20
- Reviewer/check status: reviewed
- Manual pixel/content review: completed at original 1280×720 resolution
- Panel content: contributor types, derived states, bounded duration/threshold evidence, privacy-safe hashes, and synthetic tool names only
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Alt text: contains `synthetic example data`
- Browser/OS chrome and tooltips: absent
- Prompts or prompt fragments: absent
- Real names, emails, usernames, accounts, tenants, hostnames, or organisations: absent
- Raw conversation, run, call, thread, or request IDs: absent
- Raw local paths or raw endpoints: absent
- Tool arguments or tool output: absent
- Keys, secrets, tokens, auth headers, or account IDs: absent
- Real model, provider, or account details: absent
- Misleading real-user or real-system data: absent
- Visual overclaim review: passed; contributor-level timing does not claim total turn latency or an identified root cause

## `docs/assets/dashboard-walkthrough/loki-events.png`

- Dashboard captured: Codex / Loki Logs, safe aggregate Events by name panel
- Synthetic demo profile used: `walkthrough-rich`
- Proof path used: synthetic OTLP logs → Loki raw evidence → Grafana aggregate panel
- Capture/review date: 2026-06-20
- Reviewer/check status: reviewed
- Manual pixel/content review: completed at original 1280×720 resolution
- Panel content: schema-confirmed synthetic event names and aggregate event timing only; raw log rows were deliberately excluded
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Alt text: contains `synthetic example data`
- Browser/OS chrome and tooltips: absent
- Prompts or prompt fragments: absent
- Real names, emails, usernames, accounts, tenants, hostnames, or organisations: absent
- Raw conversation, run, call, thread, or request IDs: absent
- Raw local paths, raw endpoints, or service URLs: absent
- Tool arguments or tool output: absent
- Keys, secrets, tokens, auth headers, or account IDs: absent
- Real model, provider, or account details: absent
- Misleading real-user or real-system data: absent
- Visual overclaim review: passed; this is a safe raw-signal preview, not an additional diagnostic or coverage claim

## `docs/assets/dashboard-walkthrough/tempo-traces.png`

- Dashboard captured: Codex / Tempo Traces
- Synthetic demo profile used: `walkthrough-rich`
- Proof path used: standard synthetic OTLP spans → Tempo → generated spanmetrics → Grafana
- Capture/review date: 2026-06-20
- Reviewer/check status: reviewed
- Manual pixel/content review: completed at original 1280×720 resolution
- Panel content: schema-confirmed span names carried by synthetic spans, rates, bounded latency, and span kind only; the trace-search table was kept below the captured viewport
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Alt text: contains `synthetic example data`
- Browser/OS chrome and tooltips: absent
- Prompts or prompt fragments: absent
- Real names, emails, usernames, accounts, tenants, hostnames, or organisations: absent
- Raw conversation, run, call, thread, trace, or request IDs: absent
- Raw local paths, raw endpoints, or service URLs: absent
- Tool arguments or tool output: absent
- Keys, secrets, tokens, auth headers, or account IDs: absent
- Real model, provider, or account details: absent
- Misleading real-user or real-system data: absent
- Visual overclaim review: passed; the image demonstrates synthetic trace observability without implying exhaustive coverage or a bug verdict

## `docs/assets/dashboard-walkthrough/prometheus-spanmetrics.png`

- Dashboard captured: Codex / Prometheus Metrics, Top span throughput panel
- Synthetic demo profile used: `walkthrough-rich`
- Proof path used: standard synthetic OTLP spans → Tempo → generated spanmetrics → Prometheus → Grafana
- Capture/review date: 2026-06-20
- Reviewer/check status: reviewed
- Manual pixel/content review: completed at original 1280×720 resolution
- Panel content: generated throughput for schema-confirmed span names carried by synthetic spans only; collector-wide counters were deliberately excluded
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Alt text: contains `synthetic example data`
- Browser/OS chrome and tooltips: absent
- Prompts or prompt fragments: absent
- Real names, emails, usernames, accounts, tenants, hostnames, or organisations: absent
- Raw conversation, run, call, thread, trace, or request IDs: absent
- Raw local paths, raw endpoints, or service URLs: absent
- Tool arguments or tool output: absent
- Keys, secrets, tokens, auth headers, or account IDs: absent
- Real model, provider, or account details: absent
- Misleading real-user or real-system data: absent
- Visual overclaim review: passed; generated spanmetrics are labelled as collector-derived rather than native Codex metrics

## Scope conclusion

All eight screenshots passed original-resolution privacy and overclaim review.
They are direct captures of shipped dashboards populated by local synthetic demo
data. No image contains unsafe values, browser/OS chrome, fabricated panels, or
invented metrics. The screenshots remain examples of privacy-safe investigation
evidence; they do not rank categories, establish a bug verdict, or treat silence
as proof of health.
