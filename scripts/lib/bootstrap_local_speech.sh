#!/usr/bin/env bash
# Bootstrap ASSETS/local_speech/venv (mlx-audio STT + S2S).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "SKIP local speech bootstrap (Apple Silicon only)."
  exit 0
fi

VENV="$ROOT/ASSETS/local_speech/venv"
REQ="$ROOT/requirements-local-speech.txt"

echo "=== Bootstrap local_speech venv: $VENV ==="
rm -rf "$VENV"
"$PY" -m venv "$VENV"
# shellcheck source=/dev/null
source "$VENV/bin/activate"
pip install -U pip setuptools wheel
pip install -r "$REQ"
deactivate

STT_OK=False
S2S_OK=False
if [[ -x "$VENV/bin/python" ]]; then
  if "$VENV/bin/python" "$ROOT/scripts/download_local_speech.py" --verify-stt; then
    STT_OK=True
  fi
  if "$VENV/bin/python" "$ROOT/scripts/download_local_speech.py" --verify-s2s; then
    S2S_OK=True
  fi
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  "$ROOT/.venv/bin/python" "$ROOT/scripts/select_local_speech.py" --select-only || true
  "$ROOT/.venv/bin/python" -c "
from pathlib import Path
from interview_mux.local_runtime import write_install_manifest
root = Path('$ROOT')
write_install_manifest(
    root / 'ASSETS/local_speech',
    runtime_id='speech',
    repo_url='https://github.com/Blaizzy/mlx-audio',
    repo_dir=root / 'ASSETS/local_speech',
    venv_dir=root / 'ASSETS/local_speech/venv',
    verified=$STT_OK,
)
"
  "$ROOT/.venv/bin/python" "$ROOT/scripts/ensure_warmup_voice.py" || true
fi

if [[ "$STT_OK" != "True" ]]; then
  echo "WARN: local speech STT verify failed."
else
  echo "Local speech STT OK."
fi
if [[ "$S2S_OK" != "True" ]]; then
  echo "WARN: local speech S2S verify failed (G1 synthesize unavailable)."
else
  echo "Local speech S2S OK."
fi
