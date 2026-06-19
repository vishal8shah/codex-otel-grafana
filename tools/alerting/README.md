# Codex Stuck Candidate Notification

This opt-in local feature routes recent `STUCK_CANDIDATE` evidence from the
shipped derived `codex.run_health` stream to a development webhook. Grafana does
not classify raw Codex telemetry. The run-health watcher must keep emitting the
derived snapshots that the alert rule evaluates.

## Run locally

Start the receiver before starting or recreating the stack:

```text
python tools/alerting/dev_webhook_listener.py
docker compose up -d
```

Then run the watcher in emit mode:

```text
.\scripts\watch-stuck.ps1 -EmitDerived
./scripts/watch-stuck.sh --emit-derived
```

Dry-run is the watcher default. The interval defaults to 60 seconds and can be
changed with `-IntervalSeconds 120` or `--interval-seconds 120`. Press Ctrl+C to
stop. The watcher is never silently started with the stack.

The listener binds to `0.0.0.0:9087` so the local Grafana container can reach
it through `host.docker.internal`. It accepts only `POST /grafana-alerts`, stores
only an allowlisted privacy-reduced record under the gitignored
`alert-receiver-output/` directory, and rejects payloads containing known unsafe
keys. This is a local development receiver, not a production endpoint; keep the
port behind the local machine firewall and stop it after proof.

## Alert semantics

`Codex stuck candidate detected` evaluates every minute. It selects
`STUCK_CANDIDATE` records emitted in the most recent two minutes and creates one
alert instance per unique privacy-safe `run_hash`. Repeated analyzer emissions
increase the query value but do not create additional alert instances for that
run.

This tight lookback is the conservative fallback because robust latest-row
comparison between stuck and completed states is brittle in a file-provisioned
Loki alert query. When a later `COMPLETED_RECENTLY` snapshot is emitted, no new
stuck snapshot is produced, but an earlier stuck snapshot can remain eligible
until the two-minute lookback expires, plus the next one-minute evaluation.
The alert means investigation is needed; it is not proof of a Codex bug.

Rule-specific notification routing groups by `alertname`, `grafana_folder`, and
`run_hash`, waits 10 seconds for the first group, and uses a four-hour repeat
interval. One persistent candidate should therefore notify once and suppress
unchanged repeats for four hours. The development proof can show no repeat over
several evaluations; the full four-hour boundary is documented rather than
waited out in routine validation. A resolved notification can be delayed by the
five-minute group interval even after the alert instance is no longer active;
use Grafana alert state as the immediate resolution check.

Production Slack, email, or webhook contact points are intentionally not
committed. Users must replace or extend the local contact point themselves.

## Required dependency chain

Notification works only when every link is present:

1. The LGTM/Grafana stack is running.
2. Codex telemetry is arriving.
3. The watcher/analyzer is running with derived emission enabled.
4. The alert rule is provisioned.
5. The contact point and rule-specific notification policy are configured.
6. The webhook, email, or Slack destination is reachable.

If any link is missing, silence does not prove Codex is healthy.

GitHub Actions performs static and unit validation only. Runtime OTLP, Loki,
Grafana alert evaluation, and webhook delivery remain a manual proof gate.
