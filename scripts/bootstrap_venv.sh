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
if [[ -f "$ROOT/requirements.lock" ]]; then
  echo "Installing from requirements.lock (anchor lock)..."
  pip install -r "$ROOT/requirements.lock"
else
  echo "requirements.lock missing — falling back to requirements.txt"
  pip install -r "$ROOT/requirements.txt"
fi
pip install -e "$ROOT"

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "Local LLM (default on): installing MLX deps and downloading weights if missing..."
  pip install "mlx-lm>=0.21.0" "huggingface_hub>=0.26.0" || {
    echo "WARN: mlx-lm install failed — pipeline will fall back to OpenAI-only volleys."
  }
  if python -c "import mlx_lm" 2>/dev/null; then
    REFRESH_FLAG=()
    if [[ "${LOCAL_LLM_REFRESH:-}" == "1" ]]; then
      REFRESH_FLAG=(--refresh)
    fi
    python "$ROOT/scripts/select_local_llm.py" --download "${REFRESH_FLAG[@]}" \
      || python "$ROOT/scripts/download_local_llm.py" \
        --model mlx-community/Llama-3.2-3B-Instruct-4bit \
      || echo "WARN: local LLM setup failed — install llmfit and run: python scripts/select_local_llm.py --download"
  fi
else
  echo "Note: local_llm.enabled is true by default; on non-macOS, MLX is unavailable and OpenAI volleys are used."
fi

echo "Done. Run: ./scripts/run.sh   (or: source .venv/bin/activate)"
