#!/usr/bin/env bash
# Bootstrap ASSETS/local_chatterbox/venv (ResembleAI Chatterbox clone TTS).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "SKIP local chatterbox bootstrap (Apple Silicon only)."
  exit 0
fi

VENV="$ROOT/ASSETS/local_chatterbox/venv"
REQ="$ROOT/requirements-local-chatterbox.txt"

echo "=== Bootstrap local_chatterbox venv: $VENV ==="
rm -rf "$VENV"
"$PY" -m venv "$VENV"
# shellcheck source=/dev/null
source "$VENV/bin/activate"
pip install -U pip setuptools wheel
pip install -r "$REQ"
deactivate

VERIFY_OK=False
if [[ -x "$VENV/bin/python" ]]; then
  if "$VENV/bin/python" -c "import chatterbox, torch, torchaudio"; then
    VERIFY_OK=True
  fi
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  "$ROOT/.venv/bin/python" -c "
from pathlib import Path
from interview_mux.local_runtime import write_install_manifest
root = Path('$ROOT')
write_install_manifest(
    root / 'ASSETS/local_chatterbox',
    runtime_id='chatterbox',
    repo_url='https://github.com/resemble-ai/chatterbox',
    repo_dir=root / 'ASSETS/local_chatterbox',
    venv_dir=root / 'ASSETS/local_chatterbox/venv',
    verified=$VERIFY_OK,
)
"
fi

if [[ "$VERIFY_OK" != "True" ]]; then
  echo "WARN: local chatterbox verify failed — G1 Chatterbox synthesize falls back to mlx-audio."
else
  echo "Local chatterbox OK."
fi
