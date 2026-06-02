#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

EXEC_ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi

if [[ -z "${PY:-}" || ! -x "$PY" ]]; then
  printf '\n\033[1;31mFATAL — tests/e2e bootstrap: Python 3.12+ not found\033[0m\n\n' >&2
  exit 5
fi

printf 'tests/e2e bootstrap: using %s\n' "$PY"
"$PY" -m venv "$EXEC_ROOT/.venv"
# shellcheck source=/dev/null
source "$EXEC_ROOT/.venv/bin/activate"
pip install -U pip setuptools wheel
pip install -r "$EXEC_ROOT/requirements.txt"
pip install -e "$EXEC_ROOT"
python -m playwright install chromium
printf '\ntests/e2e venv ready: %s/.venv\n' "$EXEC_ROOT"
