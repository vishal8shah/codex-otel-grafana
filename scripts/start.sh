#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose --project-directory "$repo_root" -f "$repo_root/docker-compose.yml")

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI was not found. Install and start Docker Desktop or Docker Engine first." >&2
  exit 1
fi

if [[ "${1:-}" == "--pull" ]]; then
  "${compose[@]}" pull
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--pull]" >&2
  exit 2
fi

"${compose[@]}" up --detach
"${compose[@]}" ps

echo
echo "LGTM is bound to 127.0.0.1 only. Port overrides can be set in a local .env file."
echo "Run scripts/doctor.sh, then use interactive 'codex' for telemetry validation."
