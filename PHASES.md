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

## Next One-Pain Cycle

**Tool Failure Diagnosis** is next. It must use only eligible fields recorded in
`SCHEMA.md`, preserve the privacy boundary, and prove the analyzer-to-dashboard
path before making a shipped claim.

Token burn without completion is not part of Phase 2. It was removed because
the required source shape was not schema-backed.

**Gate:** one pain per cycle. Do not promote backlog diagnostics until their
source fields and end-to-end evidence path are confirmed.
