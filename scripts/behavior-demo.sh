#!/usr/bin/env bash
set -u
command -v python3 >/dev/null 2>&1 || { printf "Python 3.10 or newer is required.\n" >&2; exit 1; }
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${script_dir}/../tools/agent-behavior/behavior_demo.py" "$@"
