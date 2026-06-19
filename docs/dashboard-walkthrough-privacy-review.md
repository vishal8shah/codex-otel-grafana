# Dashboard Walkthrough Screenshot Privacy Review

Review date: 2026-06-20

Capture method: actual file-provisioned Grafana dashboards running in the local
`grafana/otel-lgtm` stack. Focused synthetic source events were sent through
OTLP `/v1/logs`, read from Loki by the shipped analyzers, and written back as
privacy-safe derived records. Captures use a 15-minute source window and Grafana
kiosk mode so browser and operating-system chrome are absent.

Every image below was inspected at original resolution. The synthetic label is
rendered beside the image in `docs/index.html`; the source dashboard screenshot
is not altered or annotated.

## `docs/assets/dashboard-walkthrough/command-center.png`

- Dashboard captured: Codex Diagnostic Command Center
- Source data type: synthetic/local proof data
- Reviewer/check status: reviewed
- Panel titles and content: reviewed; only category names, derived counts, and investigation guidance are visible
- Tooltips: none open or visible
- Browser URL/address bar: absent from capture
- OS/window title bars: absent from capture
- Raw prompts: not visible
- Identities, account IDs, usernames, or emails: not visible
- Raw conversation IDs: not visible
- Raw local paths: not visible
- Raw endpoints: not visible
- Raw call IDs: not visible
- Tool arguments: not visible
- Tool output: not visible
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Image alt text: includes `synthetic example data`

## `docs/assets/dashboard-walkthrough/stuck-triage.png`

- Dashboard captured: Codex Stuck Triage
- Source data type: synthetic/local proof data
- Reviewer/check status: reviewed
- Panel titles and content: reviewed; one synthetic privacy-safe `run_hash`, derived state, bounded timestamps/timing, completion flag, and safe last-event type are visible
- Tooltips: none open or visible
- Browser URL/address bar: absent from capture
- OS/window title bars: absent from capture
- Raw prompts: not visible
- Identities, account IDs, usernames, or emails: not visible
- Raw conversation IDs: not visible
- Raw local paths: not visible
- Raw endpoints: not visible
- Raw call IDs: not visible
- Tool arguments: not visible
- Tool output: not visible
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Image alt text: includes `synthetic example data`

## `docs/assets/dashboard-walkthrough/tool-failure.png`

- Dashboard captured: Codex Tool Failure Diagnosis
- Source data type: synthetic/local proof data
- Reviewer/check status: reviewed
- Panel titles and content: reviewed; synthetic tool name, derived result state, privacy-safe `run_hash`, bounded timestamps, and aggregate decision/result counts are visible
- Tooltips: none open or visible
- Browser URL/address bar: absent from capture
- OS/window title bars: absent from capture
- Raw prompts: not visible
- Identities, account IDs, usernames, or emails: not visible
- Raw conversation IDs: not visible
- Raw local paths: not visible
- Raw endpoints: not visible
- Raw call IDs: not visible
- Tool arguments: not visible
- Tool output: not visible
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Image alt text: includes `synthetic example data`

## `docs/assets/dashboard-walkthrough/api-reliability.png`

- Dashboard captured: Codex API Request Reliability
- Source data type: synthetic/local proof data
- Reviewer/check status: reviewed
- Panel titles and content: reviewed; derived state, status bucket, privacy-safe run/endpoint hashes, bounded timestamps, duration, and attempt evidence are visible
- Tooltips: none open or visible
- Browser URL/address bar: absent from capture
- OS/window title bars: absent from capture
- Raw prompts: not visible
- Identities, account IDs, usernames, or emails: not visible
- Raw conversation IDs: not visible
- Raw local paths: not visible
- Raw endpoints: not visible
- Raw call IDs: not visible
- Tool arguments: not visible
- Tool output: not visible
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Image alt text: includes `synthetic example data`

## `docs/assets/dashboard-walkthrough/slow-contributor.png`

- Dashboard captured: Codex Slow Contributor Triage
- Source data type: synthetic/local proof data
- Reviewer/check status: reviewed
- Panel titles and content: reviewed; contributor type, derived state, bounded duration/threshold, privacy-safe hashes, synthetic tool name, and bounded timestamps are visible
- Tooltips: none open or visible
- Browser URL/address bar: absent from capture
- OS/window title bars: absent from capture
- Raw prompts: not visible
- Identities, account IDs, usernames, or emails: not visible
- Raw conversation IDs: not visible
- Raw local paths: not visible
- Raw endpoints: not visible
- Raw call IDs: not visible
- Tool arguments: not visible
- Tool output: not visible
- Visible nearby label: `Synthetic example data` is present in the containing figure
- Image alt text: includes `synthetic example data`

## Scope conclusion

All five screenshots passed review. They show real shipped dashboards populated by
local synthetic proof data. No image contains raw or unsafe values, browser/OS
chrome, fabricated panels, or invented metrics. The screenshots remain examples
of investigation evidence; they do not prove a Codex bug or a healthy system.
