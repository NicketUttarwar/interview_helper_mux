#!/usr/bin/env bash
# Bootstrap ASSETS/local_llm/venv (MLX volley framer).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "SKIP local LLM bootstrap (Apple Silicon only)."
  exit 0
fi

VENV="$ROOT/ASSETS/local_llm/venv"
REQ="$ROOT/requirements-local-llm.txt"
[[ -f "$REQ" ]] || REQ="$ROOT/requirements-local-mlx.txt"

echo "=== Bootstrap local_llm venv: $VENV ==="
rm -rf "$VENV"
"$PY" -m venv "$VENV"
# shellcheck source=/dev/null
source "$VENV/bin/activate"
pip install -U pip setuptools wheel
pip install -r "$REQ"
deactivate

VERIFIED=False
if [[ -x "$VENV/bin/python" ]]; then
  if "$VENV/bin/python" "$ROOT/scripts/download_local_llm.py" --verify >/dev/null 2>&1; then
    VERIFIED=True
  fi
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  "$ROOT/.venv/bin/python" -c "
from pathlib import Path
from interview_mux.local_runtime import write_install_manifest
root = Path('$ROOT')
write_install_manifest(
    root / 'ASSETS/local_llm',
    runtime_id='mlx',
    repo_url='https://github.com/ml-explore/mlx-lm',
    repo_dir=root / 'ASSETS/local_llm',
    venv_dir=root / 'ASSETS/local_llm/venv',
    verified=$VERIFIED,
)
"
fi

if [[ "$VERIFIED" != "True" ]]; then
  echo "WARN: local LLM venv verify failed — volley framer will fail-open."
else
  echo "Local LLM venv OK."
fi
