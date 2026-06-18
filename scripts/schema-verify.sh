#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"

printf 'Codex OTel schema verification assistant\n'
printf 'WARNING: Interactive codex is required for full metrics verification.\n'
printf 'WARNING: Do not use codex exec for metrics discovery; it can produce a false negative.\n'
printf 'WARNING: codex mcp-server is currently not observable through Codex OTel.\n'
printf 'This script checks prerequisites and prints query hints. It does not claim that a signal exists or is absent.\n\n'

GRAFANA_URL="$GRAFANA_URL" bash "$SCRIPT_DIR/doctor.sh"
doctor_exit=$?
config_failures=0

config_path="${CODEX_CONFIG_PATH:-${HOME}/.codex/config.toml}"
printf '\nUser-level OTel config checks: %s\n' "$config_path"
if [[ -f "$config_path" ]]; then
  if grep -Eq '^[[:space:]]*\[otel\][[:space:]]*$' "$config_path"; then
    printf '[PASS] [otel] section\n'
    otel_config="$(awk '
      /^[[:space:]]*\[otel\][[:space:]]*$/ { in_otel=1; next }
      /^[[:space:]]*\[[^]]+\][[:space:]]*$/ { if (in_otel) exit }
      in_otel { print }
    ' "$config_path")"
  else
    printf '[MISSING] [otel] section\n'
    config_failures=$((config_failures + 1))
    otel_config=''
  fi

  config_check() {
    local label="$1" pattern="$2"
    if grep -Eq "$pattern" <<<"$otel_config"; then
      printf '[PASS] %s\n' "$label"
    else
      printf '[MISSING] %s\n' "$label"
      config_failures=$((config_failures + 1))
    fi
  }
  config_check "exporter" '^[[:space:]]*exporter[[:space:]]*='
  config_check "metrics_exporter" '^[[:space:]]*metrics_exporter[[:space:]]*='
  config_check "trace_exporter" '^[[:space:]]*trace_exporter[[:space:]]*='
  config_check "log_user_prompt = false" '^[[:space:]]*log_user_prompt[[:space:]]*=[[:space:]]*false([[:space:]]*(#.*)?)?$'
else
  printf '[MISSING] User-level config. Schema verification cannot proceed until OTel is configured.\n'
  config_failures=$((config_failures + 1))
fi

cat <<'EOF'

Manual discovery procedure:
1. Start an interactive session by running: codex
2. Submit a tiny, non-sensitive prompt manually.
3. Exercise a harmless tool path only if tool telemetry is under test.
4. Exit Codex cleanly so the OTel exporters can flush.
5. Wait briefly, then run the queries below in Grafana Explore.

Loki query hints (field existence must be confirmed from returned records):
  {service_name="Codex Desktop"} | event_name="codex.sse_event"
  {service_name="Codex Desktop"} | event_name="codex.sse_event" | event_kind="response.completed"
  {service_name="Codex Desktop"} | event_name="codex.tool_decision"
  {service_name="Codex Desktop"} | event_name="codex.tool_result"

Prometheus query hints (OTLP names may be normalized; use the metric browser):
  {__name__=~"codex_.*"}
  codex_conversation_starts_total
  codex_api_request_total
  codex_tool_call_total
  codex_tool_call_duration_ms_bucket

Tempo TraceQL query hints:
  { resource.service.name = "Codex Desktop" }
  { resource.service.name = "Codex Desktop" && name = "codex.tool.call" }

Terms to verify, not assume:
  codex.conversation_starts, codex.api_request, codex.sse_event,
  response.completed, codex.tool_decision, codex.tool_result,
  codex.tool.call, codex.tool.call.duration_ms

Record sanitized evidence manually in SCHEMA.md. A metrics result obtained with
codex exec is invalid for full schema verification.
EOF

if [[ "$doctor_exit" != "0" ]] || (( config_failures > 0 )); then
  exit 1
fi
