#!/usr/bin/env bash
# Bootstrap isolated venv for local MusicGen (music-only theme stems).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${MUX_MUSICGEN_VENV:-$ROOT/ASSETS/local_musicgen/venv}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
CACHE_DIR="${MUX_MUSICGEN_CACHE:-$ROOT/ASSETS/local_musicgen/hf_cache}"
PREFETCH="${MUX_MUSICGEN_PREFETCH:-1}"

mkdir -p "$(dirname "$VENV")" "$CACHE_DIR"
if [[ ! -d "$VENV" ]]; then
  "$PYTHON_BIN" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -U pip wheel
# Prefer lightweight deps; MusicGen weights download on first generate / prefetch.
python -m pip install "numpy" "scipy" "torch" "torchaudio" "transformers" || true
# Optional MLX ports when available on Apple Silicon.
python -m pip install "mlx" || true
python -m pip install "mlx-audiogen" || python -m pip install "musicgen-mlx" || true

MODEL_IDS=(
  "facebook/musicgen-large"
  "facebook/musicgen-melody-large"
  "facebook/musicgen-medium"
  "facebook/musicgen-small"
)

if [[ "$PREFETCH" == "1" ]]; then
  echo "Prefetching MusicGen weights into $CACHE_DIR ..."
  export HF_HOME="$CACHE_DIR"
  export TRANSFORMERS_CACHE="$CACHE_DIR"
  for mid in "${MODEL_IDS[@]}"; do
    python - <<PY || echo "WARN: prefetch failed for $mid (will download on first generate)"
from transformers import AutoProcessor
try:
    from transformers import MusicgenForConditionalGeneration as M
except Exception:
    M = None
try:
    from transformers import MusicgenMelodyForConditionalGeneration as MM
except Exception:
    MM = None
mid = "$mid"
print("prefetch", mid)
AutoProcessor.from_pretrained(mid)
if "melody" in mid and MM is not None:
    MM.from_pretrained(mid)
elif M is not None:
    M.from_pretrained(mid)
print("ok", mid)
PY
  done
fi

echo "MusicGen venv ready at $VENV"
echo "Default model: facebook/musicgen-large (melody: facebook/musicgen-melody-large)"
echo "HF cache: $CACHE_DIR"
