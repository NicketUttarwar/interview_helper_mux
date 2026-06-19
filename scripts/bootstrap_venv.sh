#!/usr/bin/env bash
# =============================================================================
# SINGLE SETUP ENTRY — interview_helper_mux
#
# Creates/refreshes ALL Python environments for this repo:
#
#   1. Core .venv          — interview_mux package + FastAPI GUI (requirements.lock)
#   2. ASSETS/local_llm/venv       — MLX volley framing (requirements-local-mlx.txt)
#   3. ASSETS/local_deepfilter/venv — DeepFilterNet preclean (requirements-local-deepfilter.txt)
#   4. ASSETS/local_mmaudio/venv    — MMAudio SFX generation (requirements-local-mmaudio.txt)
#
# Also:
#   - git clone/pull upstream repos into ASSETS/local_* (see clone_local_audio_repos.sh)
#   - verify each local runtime (--verify gate; non-zero exit on failure)
#   - write ASSETS/local_*/install.json manifests
#   - on macOS Apple Silicon: download MLX LLM weights (llmfit or default fallback)
#   - optional faster-whisper weights for disfluency_extract
#   - run scripts/verify_local_models.sh (skip with BOOTSTRAP_SKIP_VERIFY=1)
#
# If you delete any venv or clone tree, re-run THIS script — do not use separate
# bootstrap scripts. Internal helper: scripts/lib/bootstrap_local_runtimes.sh
#
# After bootstrap:
#   source .venv/bin/activate
#   ./scripts/verify_local_models.sh
#   ./tools/check_prerequisites.sh
#   CHECK_LOCAL_RUNTIMES=1 ./tools/check_prerequisites.sh   # strict local stack check
#
# Docs: SETUP.md · docs/cross-cutting/local-audio-stack.md
# =============================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 || command -v python3)"
fi
echo "Using Python: $PY"
echo "=== Core application venv (.venv) ==="
"$PY" -m venv "$ROOT/.venv"
# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
pip install -U pip setuptools wheel
if [[ -f "$ROOT/requirements.lock" ]]; then
  echo "Installing from requirements.lock (anchor lock)…"
  pip install -r "$ROOT/requirements.lock"
else
  echo "requirements.lock missing — falling back to requirements.txt"
  pip install -r "$ROOT/requirements.txt"
fi
pip install -e "$ROOT"

echo "=== Local audio repos + isolated ASSETS venvs ==="
bash "$ROOT/scripts/lib/bootstrap_local_runtimes.sh"

if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  echo "=== Local LLM (MLX weights) ==="
  if command -v llmfit >/dev/null 2>&1; then
    python "$ROOT/scripts/select_local_llm.py" --download --verify \
      || echo "WARN: local LLM setup failed — OpenAI volley fallback remains available."
  elif python "$ROOT/scripts/download_local_llm.py" --verify 2>/dev/null; then
    echo "MLX weights already present (llmfit not installed; using existing cache)."
  else
    echo "llmfit not on PATH — downloading default MLX model."
    echo "  Hardware-aware pick: brew install AlexsJones/llmfit/llmfit"
    MLX_PY="$ROOT/ASSETS/local_llm/venv/bin/python"
    if [[ -x "$MLX_PY" ]]; then
      "$MLX_PY" "$ROOT/scripts/download_local_llm.py" \
        --model mlx-community/Llama-3.2-3B-Instruct-4bit --verify \
        || echo "WARN: local LLM download failed — run: python scripts/select_local_llm.py --download"
    else
      echo "WARN: MLX venv missing — re-run bootstrap after fixing errors above."
    fi
  fi
fi

echo "Local STT (optional): prefetch faster-whisper weights for disfluency_extract…"
python "$ROOT/scripts/download_local_stt.py" --model base \
  || echo "WARN: local STT download skipped — disfluency_extract will use transcript lexicon only."

if [[ "${BOOTSTRAP_SKIP_VERIFY:-0}" != "1" ]]; then
  echo "=== Verify local model stacks ==="
  bash "$ROOT/scripts/verify_local_models.sh" \
    || echo "WARN: verify_local_models reported failures — fix before preclean/SFX stages."
fi

echo "Done. Run: ./scripts/run.sh   (or: source .venv/bin/activate)"
