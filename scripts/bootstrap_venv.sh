#!/usr/bin/env bash
# =============================================================================
# SINGLE SETUP ENTRY — interview_helper_mux
#
# Creates/refreshes ALL environments and builds the GUI bundle:
#
#   1. Core .venv          — interview_mux + dev tools (scripts/lib/install_core_venv.sh)
#   2. Frontend            — npm ci + React build (scripts/lib/install_frontend.sh)
#   3. ASSETS/local_llm/venv       — MLX volley framing
#   4. ASSETS/local_deepfilter/venv — DeepFilterNet preclean
#   5. ASSETS/local_mmaudio/venv    — MMAudio SFX generation
#
# Also: clone/pull local audio repos, MLX weights (macOS), optional STT weights,
# verify gates, install.json manifests.
#
# After install:
#   ./scripts/run.sh
#
# Skip GUI during install:  BOOTSTRAP_SKIP_GUI=1 ./scripts/install.sh
# Skip local verify:        BOOTSTRAP_SKIP_VERIFY=1 ./scripts/install.sh
#
# Docs: SETUP.md · docs/cross-cutting/local-audio-stack.md
# =============================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Core application venv (.venv) ==="
bash "$ROOT/scripts/lib/install_core_venv.sh"

if [[ "${BOOTSTRAP_SKIP_GUI:-0}" != "1" ]]; then
  bash "$ROOT/scripts/lib/install_frontend.sh"
else
  echo "=== Frontend GUI — skipped (BOOTSTRAP_SKIP_GUI=1) ==="
fi

echo "=== Local audio repos + isolated ASSETS venvs ==="
bash "$ROOT/scripts/lib/bootstrap_local_runtimes.sh"

if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  echo "=== Local LLM (MLX weights) ==="
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"
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
      echo "WARN: MLX venv missing — re-run install after fixing errors above."
    fi
  fi
fi

echo "Local STT (optional): prefetch faster-whisper weights for disfluency_extract …"
# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
python "$ROOT/scripts/download_local_stt.py" --model base \
  || echo "WARN: local STT download skipped — disfluency_extract will use transcript lexicon only."

if [[ "${BOOTSTRAP_SKIP_VERIFY:-0}" != "1" ]]; then
  echo "=== Verify local model stacks ==="
  bash "$ROOT/scripts/verify_local_models.sh" \
    || echo "WARN: verify_local_models reported failures — fix before preclean/SFX stages."
fi

echo ""
echo "Install complete."
echo "  Launch GUI:  ./scripts/run.sh"
echo "  Activate:    source .venv/bin/activate"
