#!/usr/bin/env bash
# Full first-time / refresh install — alias for bootstrap_venv.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$ROOT/scripts/bootstrap_venv.sh" "$@"
