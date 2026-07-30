#!/usr/bin/env bash
# Bootstrap isolated venv for local MLX MusicGen (music-only theme stems).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${MUX_MUSICGEN_VENV:-$ROOT/ASSETS/local_musicgen/venv}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

mkdir -p "$(dirname "$VENV")"
if [[ ! -d "$VENV" ]]; then
  "$PYTHON_BIN" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -U pip wheel
# Prefer lightweight deps; MusicGen weights download on first generate.
python -m pip install "numpy" "scipy" "torch" "torchaudio" "transformers" || true
# Optional MLX ports when available on Apple Silicon.
python -m pip install "mlx" || true
python -m pip install "mlx-audiogen" || python -m pip install "musicgen-mlx" || true
echo "MusicGen venv ready at $VENV"
echo "Default model: facebook/musicgen-medium (downloaded on first generation)"
