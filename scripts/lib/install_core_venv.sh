#!/usr/bin/env bash
# Core application .venv — single source of truth for pip installs.
# Called by scripts/bootstrap_venv.sh and optionally MUX_REFRESH_DEPS=1 ./scripts/run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$ROOT/.venv"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 2>/dev/null || command -v python3)"
fi

if [[ ! -x "$PY" ]]; then
  echo "ERROR: Python 3.12+ not found. Set PYTHON= or install python@3.12." >&2
  exit 1
fi

echo "Using Python: $PY"

if [[ ! -d "$VENV" ]]; then
  echo "Creating virtual environment at .venv ..."
  "$PY" -m venv "$VENV"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

echo "Upgrading pip / setuptools / wheel ..."
pip install -U pip setuptools wheel

if [[ -f "$ROOT/requirements.lock" ]]; then
  echo "Installing from requirements.lock (anchor lock) ..."
  pip install -r "$ROOT/requirements.lock"
else
  echo "requirements.lock missing — falling back to requirements.txt"
  pip install -r "$ROOT/requirements.txt"
fi

echo "Installing interview-mux editable + dev tools (pytest, ruff, pip-audit) ..."
pip install -e "${ROOT}[dev]"

# requirements.lock can lag requirements.txt (Pillow/boto3 for cover + S3 publish).
echo "Ensuring cover/publish extras (Pillow, boto3) ..."
pip install 'boto3>=1.35,<2' 'Pillow>=10,<12'

python -c "import interview_mux; print('interview_mux', interview_mux.__version__, 'OK')"
