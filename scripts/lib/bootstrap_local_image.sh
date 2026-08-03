#!/usr/bin/env bash
# Bootstrap ASSETS/local_image/venv (MLX text-to-image). Fail-open WARN.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "SKIP local_image bootstrap (Apple Silicon only)."
  exit 0
fi

VENV="$ROOT/ASSETS/local_image/venv"
REQ="$ROOT/requirements-local-image.txt"

echo "=== Bootstrap local_image venv: $VENV ==="
rm -rf "$VENV"
"$PY" -m venv "$VENV"
# shellcheck source=/dev/null
source "$VENV/bin/activate"
pip install -U pip setuptools wheel
if [[ -f "$REQ" ]]; then
  pip install -r "$REQ" || echo "WARN: local_image pip install had errors"
else
  echo "WARN: missing $REQ"
fi
deactivate

# Select + optionally download
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  "$ROOT/.venv/bin/python" "$ROOT/scripts/select_local_image.py" --download || \
    echo "WARN: select_local_image failed — cover gen will fail-open to show art"
fi

VERIFIED=False
if [[ -x "$VENV/bin/python" ]]; then
  if "$VENV/bin/python" "$ROOT/scripts/download_local_image.py" --verify >/dev/null 2>&1; then
    VERIFIED=True
  fi
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  "$ROOT/.venv/bin/python" -c "
from pathlib import Path
from interview_mux.local_runtime import write_install_manifest
root = Path('$ROOT')
write_install_manifest(
    root / 'ASSETS/local_image',
    runtime_id='image',
    repo_url='https://github.com/ml-explore/mlx',
    repo_dir=root / 'ASSETS/local_image',
    venv_dir=root / 'ASSETS/local_image/venv',
    verified=$VERIFIED,
)
"
fi

if [[ "$VERIFIED" != "True" ]]; then
  echo "WARN: local_image verify failed — episode covers fail-open to show art."
else
  echo "Local image venv OK."
fi
