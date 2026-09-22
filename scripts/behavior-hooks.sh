#!/usr/bin/env bash
set -u
command -v python3 >/dev/null 2>&1 || { printf "Python 3.10 or newer is required.\n" >&2; exit 1; }
if [[ $# -lt 1 ]]; then printf "Usage: behavior-hooks.sh install|check|remove\n" >&2; exit 2; fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${script_dir}/../tools/agent-behavior/behavior_hooks.py" "$1" --root "${script_dir}/.." "${@:2}"
