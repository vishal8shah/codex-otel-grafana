#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose --project-directory "$repo_root" -f "$repo_root/docker-compose.yml")

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI was not found. Install and start Docker Desktop or Docker Engine first." >&2
  exit 1
fi

container_name="$("${compose[@]}" config | awk '$1 == "container_name:" { print $2; exit }')"
compose_project="$("${compose[@]}" config | awk '$1 == "name:" { print $2; exit }')"

if docker inspect "$container_name" >/dev/null 2>&1; then
  existing_project="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$container_name")"
  if [[ -z "$existing_project" ]]; then
    existing_image="$(docker inspect --format '{{.Config.Image}}' "$container_name")"
    data_volume="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "$container_name")"
    if [[ "$existing_image" != grafana/otel-lgtm:* || "$data_volume" != "codex-otel-lgtm-data" ]]; then
      echo "Container '$container_name' already exists and is not a recognized legacy LGTM container." >&2
      exit 1
    fi

    echo "Migrating legacy LGTM container '$container_name' to Docker Compose; preserving volume '$data_volume'."
    docker rm --force "$container_name" >/dev/null
  elif [[ "$existing_project" != "$compose_project" ]]; then
    echo "Container '$container_name' belongs to Compose project '$existing_project', not '$compose_project'." >&2
    exit 1
  fi
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
