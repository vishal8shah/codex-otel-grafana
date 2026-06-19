# Delivery Phases

1. **Phase 0: schema evidence — shipped**
   Established observed fields, entrypoint limitations, privacy boundaries,
   connectivity checks, and explicit unknowns.
2. **Phase 1: local LGTM setup — shipped**
   Made local stack installation and configuration reproducible across Windows,
   macOS, and Linux.
3. **Phase 1b: file-provisioned dashboards — shipped**
   Added repository-owned Grafana datasource and dashboard provisioning.
4. **Phase 2: Codex Stuck Triage — shipped**
   Added one privacy-safe, issue-led diagnostic using confirmed raw telemetry,
   derived `codex.run_health`, and unique `run_hash` stat counting.
5. **Phase 3: Codex Tool Failure Diagnosis — shipped**
   Adds one focused diagnostic using confirmed tool decision/result logs,
   privacy-safe `run_hash`, and clearly derived `codex.tool_diagnostic` records.
6. **Phase 4: Codex API Request Reliability — shipped**
   Adds one focused diagnostic using confirmed `codex.api_request` logs,
   privacy-safe run/endpoint hashes, and derived `codex.api_diagnostic` records.
7. **Phase 5: Codex Slow Contributor Triage — shipped**
   Identifies slow schema-confirmed API and tool contributor groups without
   claiming full end-to-end turn latency.
8. **Phase 6: Codex Stuck Candidate Notification — shipped**
   Adds one opt-in watcher and development-safe Grafana notification path for
   recent privacy-safe `STUCK_CANDIDATE` derived evidence.
   This proves the push path, but not a fully trustworthy relied-on mid-session
   monitor. A future phase should consider watcher heartbeat, no-data
   visibility, or alert-path health checks.

## Next One-Pain Cycle

**Review/resume flow diagnosis** is next in the existing backlog. It remains
unbuilt until its source fields, privacy boundary, and end-to-end evidence path
are confirmed.

Token burn without completion is not part of Phase 2. It was removed because
the required source shape was not schema-backed.

**Gate:** one pain per cycle. Do not promote backlog diagnostics until their
source fields and end-to-end evidence path are confirmed.
