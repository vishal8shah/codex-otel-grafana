#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose --project-directory "$repo_root" -f "$repo_root/docker-compose.yml")

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI was not found." >&2
  exit 1
fi

if [[ "${1:-}" == "--remove" ]]; then
  "${compose[@]}" down
  echo "Removed the Compose container and network. The named data volume was preserved."
elif [[ $# -eq 0 ]]; then
  "${compose[@]}" stop
else
  echo "Usage: $0 [--remove]" >&2
  exit 2
fi
