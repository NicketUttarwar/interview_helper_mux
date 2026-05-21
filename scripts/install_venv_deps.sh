#!/usr/bin/env bash
# Refresh Python deps in the existing .venv (idempotent).
# Requires .venv built with Python 3.12+ native arm64 — else run ./scripts/bootstrap_venv.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PY="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "No .venv found. Run: ./scripts/bootstrap_venv.sh" >&2
  exit 1
fi

echo "=== install deps into $PY ==="
"$PY" -m pip install --upgrade pip wheel
"$PY" -m pip install --prefer-binary -r requirements.txt
"$PY" tools/verify_install.py
echo "=== done ==="
