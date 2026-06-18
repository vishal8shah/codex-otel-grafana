#!/usr/bin/env bash
set -u

strict=0
if [[ "${1:-}" == "--strict" ]]; then
  strict=1
elif [[ $# -gt 0 ]]; then
  printf 'Usage: %s [--strict]\n' "$0" >&2
  exit 2
fi

GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
CONTAINER_NAME="${CONTAINER_NAME:-codex-otel-lgtm}"
CODEX_CONFIG_PATH="${CODEX_CONFIG_PATH:-${HOME}/.codex/config.toml}"
failures=0

check() {
  local name="$1" result="$2" detail="$3" required="${4:-1}"
  if [[ "$result" == "0" ]]; then
    printf '[PASS] %s: %s\n' "$name" "$detail"
  elif [[ "$required" == "0" ]]; then
    printf '[INFO] %s: %s\n' "$name" "$detail"
  else
    printf '[FAIL] %s: %s\n' "$name" "$detail"
    failures=$((failures + 1))
  fi
}

tcp_open() {
  local host="$1" port="$2"
  if command -v nc >/dev/null 2>&1; then
    nc -z -w 2 "$host" "$port" >/dev/null 2>&1
  elif command -v timeout >/dev/null 2>&1; then
    timeout 2 bash -c "</dev/tcp/$host/$port" >/dev/null 2>&1
  else
    return 2
  fi
}

printf 'Codex Observability Kit doctor (connectivity and setup health only)\n'
printf 'This command does not discover telemetry schema or validate metric emission.\n\n'

command -v docker >/dev/null 2>&1; check "Docker CLI" "$?" "docker"
docker info >/dev/null 2>&1; docker_ok=$?; check "Docker engine" "$docker_ok" "local engine"

container_ok=1
if [[ "$docker_ok" == "0" ]] && [[ "$(docker ps --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}' 2>/dev/null)" == "$CONTAINER_NAME" ]]; then
  container_ok=0
fi
check "LGTM container" "$container_ok" "$CONTAINER_NAME"

curl -fsS --max-time 3 "$GRAFANA_URL/api/health" >/dev/null 2>&1
check "Grafana" "$?" "$GRAFANA_URL"

tcp_open localhost 4318; http_port=$?
if [[ "$http_port" == "2" ]]; then
  printf '[SKIP] OTLP HTTP port: install nc or timeout for a TCP check\n'
else
  check "OTLP HTTP port" "$http_port" "localhost:4318"
fi

tcp_open localhost 4317; grpc_port=$?
if [[ "$grpc_port" == "2" ]]; then
  printf '[SKIP] OTLP gRPC port: install nc or timeout for a TCP check\n'
else
  check "OTLP gRPC port" "$grpc_port" "localhost:4317"
fi

command -v codex >/dev/null 2>&1; codex_ok=$?
if [[ "$codex_ok" == "0" ]]; then
  codex_version="$(codex --version 2>/dev/null)"; codex_run=$?
  codex_detail="${codex_version:-$(command -v codex)}"
  check "Codex CLI" "$codex_run" "$codex_detail" "$strict"
else
  check "Codex CLI" 1 "not found on PATH" "$strict"
fi

[[ -f "$CODEX_CONFIG_PATH" ]]; check "User Codex config" "$?" "$CODEX_CONFIG_PATH" "$strict"

printf '\nStack health determines the default exit code. Use --strict to require Codex CLI and config readiness.\n'
printf 'Run schema-verify separately for discovery guidance.\n'
(( failures == 0 ))
