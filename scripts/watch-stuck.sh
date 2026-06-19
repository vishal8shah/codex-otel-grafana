#!/usr/bin/env bash
set -u

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
interval_seconds=60
mode="dry-run"
analyzer_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --emit-derived)
      mode="emit-derived"
      shift
      ;;
    --interval-seconds)
      if [[ $# -lt 2 || ! "$2" =~ ^[0-9]+$ || "$2" -lt 15 ]]; then
        echo "--interval-seconds requires an integer of at least 15." >&2
        exit 2
      fi
      interval_seconds="$2"
      shift 2
      ;;
    --)
      shift
      analyzer_args+=("$@")
      break
      ;;
    *)
      analyzer_args+=("$1")
      shift
      ;;
  esac
done

stopped=0
stop_watcher() {
  stopped=1
  printf '\nCodex stuck watcher stopped.\n'
}
trap stop_watcher INT TERM

printf 'Codex stuck watcher: mode=%s interval_seconds=%s\n' "$mode" "$interval_seconds"
printf 'Press Ctrl+C to stop. The watcher is opt-in and is not started by the LGTM stack.\n'

while [[ "$stopped" -eq 0 ]]; do
  if [[ "$mode" == "emit-derived" ]]; then
    "${script_dir}/run-health.sh" --emit-derived "${analyzer_args[@]}" || exit $?
  else
    "${script_dir}/run-health.sh" "${analyzer_args[@]}" || exit $?
  fi

  sleep "$interval_seconds" &
  wait $! || true
done
