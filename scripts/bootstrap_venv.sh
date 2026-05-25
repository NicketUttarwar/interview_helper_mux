#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi
echo "Using Python: $PY"
"$PY" -m venv "$ROOT/.venv"
# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
pip install -U pip setuptools wheel
pip install -r "$ROOT/requirements.txt"
pip install "$ROOT"
pip install "pytest>=8,<9"
echo "Done. Run: ./scripts/run.sh   (or: source .venv/bin/activate)"
