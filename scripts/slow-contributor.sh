#!/usr/bin/env bash
set -u

if ! command -v python3 >/dev/null 2>&1; then
  printf "Python 3.10 or newer is required. Install Python and ensure 'python3' is on PATH.\n" >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
mode="--dry-run"
if [[ "${1:-}" == "--emit-derived" ]]; then
  mode="--emit-derived"
  shift
fi

exec python3 "${repo_root}/tools/slow-contributor/slow_contributor.py" "$mode" "$@"
