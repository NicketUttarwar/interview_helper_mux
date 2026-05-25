#!/usr/bin/env bash
# Run interview_helper_mux web GUI. Any failure exits the whole process.
# Pass --cli for headless pipeline mode (legacy).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 2>/dev/null || command -v python3)"
fi

if [[ ! -d "$VENV" ]]; then
  echo "Creating virtual environment at .venv ..."
  "$PY" -m venv "$VENV"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

pip install -q -U pip setuptools wheel
pip install -q -r "$ROOT/requirements.txt"
pip install -q "$ROOT"

if [[ "${1:-}" == "--cli" ]]; then
  shift
  exec python -m interview_mux "$@"
fi

exec python -m interview_mux serve "$@"
