# Codex Agent Behaviour Security

This Phase 8 extension records privacy-safe evidence about supported local Codex
hook activity and derives deterministic investigation findings. It is informed
by publicly documented agent-incident patterns, but it does not infer private
reasoning, intent, deception, reward hacking, concealment, or goal drift.

## Safety model

- Observation is the default. Enforcement must be selected explicitly.
- Raw hook payloads are inspected only in memory and are never written or sent.
- OTLP observations contain HMAC-derived identifiers, enums, rule IDs, bounded
  counters, timestamps, and fixed explanatory text only.
- Dangerous demo actions are strings inside an in-memory synthetic fixture.
  They are classified, never executed.
- Hooks cover supported local function-tool paths. Hosted tools and specialized
  paths can bypass hooks, so this is not a complete enforcement boundary.

## Quick demo

Start the existing local stack, then emit the incident-safe synthetic profile:

```powershell
.\scripts\start.ps1
.\scripts\behavior-demo.ps1 --profile incident-safe
.\scripts\behavior-analyze.ps1 -EmitDerived
```

```bash
./scripts/start.sh
./scripts/behavior-demo.sh --profile incident-safe
./scripts/behavior-analyze.sh --emit-derived
```

Open **Grafana > Codex Agent Behaviour Security**. The profile includes normal
activity, tool recovery, approval evidence, repeated probing, credential-to-
egress correlation, blocked destructive/persistence/public-mutation patterns,
subagent fan-out, compaction, interruption, and heartbeat/no-data guidance.

## Demo deck and presentation flow

Open [`docs/agent-behavior-demo-deck.html`](../../docs/agent-behavior-demo-deck.html)
directly in a browser for the self-contained 12-slide walkthrough. It explains
the implementation, the meaning of all 12 dashboard panels, correlation and
privacy boundaries, the five-minute incident-safe demo, and the handoff to the
live Grafana dashboard. Its screenshots are real local Grafana captures using
labelled synthetic evidence.

Keep these evidence types separate while presenting:

1. native Codex OTel evidence for API, streaming, tool-result, metric, and trace
   activity;
2. real hook-derived observations from a harmless local session;
3. labelled synthetic incident observations and findings; and
4. deterministic enforcement decisions and correlations.

The deck is explanatory material, not additional runtime evidence. Rebuild its
embedded screenshots after changing source images with
`node scripts/embed-agent-behavior-deck-images.mjs`. For local review, run
`node scripts/preview-agent-behavior-deck.mjs` and open
`http://127.0.0.1:8765`.

## Opt-in live hook proof

Install repository-local hooks; this never modifies the user-level Codex config:

```powershell
.\scripts\behavior-hooks.ps1 install
.\scripts\behavior-hooks.ps1 check
```

```bash
./scripts/behavior-hooks.sh install
./scripts/behavior-hooks.sh check
```

Codex will ask whether to trust repository hooks. With the stack running, start
interactive `codex` in this repository and submit a harmless prompt such as:

```text
Run a read-only command that prints the word behaviour-demo, then stop.
```

Exit cleanly and verify arrival:

```powershell
.\scripts\behavior-demo.ps1 --verify-live
```

Remove only this monitor's handlers and local HMAC key with:

```powershell
.\scripts\behavior-hooks.ps1 remove
```

The installer preserves unrelated repository hooks. `.codex/hooks.json` and
`.codex/behavior-monitor.key` are gitignored local state.

## Enforcement demo

The installed hook remains observe-only. To exercise enforcement safely, pass
`--mode enforce --synthetic --dry-run` to `behavior-monitor` with a synthetic
fixture, or use the incident-safe demo. Do not use a real destructive command
to test the policy.

High/critical pre-tool rules can deny broad deletion, sensitive-resource reads,
control bypass, outbound credential use, public mutation, persistence creation,
and explicit workspace-boundary access. Medium-risk rules only observe.
Post-tool findings cannot undo completed side effects.

For current local Bash hooks, `PostToolUse.tool_response` may be model-facing
text without a reliable exit-status field. Such results remain `observed`; the
monitor emits `completed` or `failed` only when a supported structured response
contains an explicit success indicator. Do not infer success from text output.

## Evidence streams

| Stream | Producer | Meaning |
|---|---|---|
| `codex.behavior_observation` | Hook adapter | One privacy-safe lifecycle, tool, approval, subagent, or policy observation |
| `codex.behavior_finding` | Windowed analyzer | One deterministic single-signal or correlated run-window finding |
| `codex.behavior_analyzer_heartbeat` | Windowed analyzer | One bounded liveness record for each completed analyzer run, including runs with no findings |

`policy.json` is versioned and defaults to `observe`. In enforcement mode,
policy evaluation failure blocks the pending supported hook action. In observe
mode, failure is visible but does not change the tool decision.

## Public commands

- `behavior-monitor` normalizes one hook event from stdin.
- `behavior-analyze` queries Loki or a privacy-safe fixture and emits findings.
- `behavior-demo --profile incident-safe` runs the side-effect-free demo.
- `behavior-doctor` checks policy, hooks, stack reachability, provisioning, and a recent analyzer heartbeat in Loki.
- `behavior-hooks install|check|remove` manages repository-local hook state.

PowerShell and shell wrappers for each command live under `scripts/`.

## Known limits

The monitor does not observe private chain-of-thought, semantic intent,
packet-level traffic, OS-level file access, inter-agent message content, all
hosted tools, or production SOC/SIEM controls. A missing heartbeat, empty panel,
or absent alert is not health evidence. Findings support investigation; they do
not prove malicious behaviour or a Codex defect.
