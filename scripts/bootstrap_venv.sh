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
# Local LLM (Apple Silicon): hardware-aware llmfit pick → selection.json +
# weights (reuse when already present) → capability_manifest.json. No model id
# in secrets.env — resolve at runtime from selection.json.
#
# Force llmfit re-pick: LOCAL_LLM_REFRESH=1 ./scripts/bootstrap_venv.sh
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
  echo "=== Local LLM (MLX: select + download + calibrate) ==="
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"

  _SELECT_ARGS=(--download --verify)
  if [[ "${LOCAL_LLM_REFRESH:-0}" == "1" ]]; then
    echo "LOCAL_LLM_REFRESH=1 — re-running llmfit (ignoring cached selection.json)"
    _SELECT_ARGS+=(--refresh)
  fi

  if command -v llmfit >/dev/null 2>&1; then
    python "$ROOT/scripts/select_local_llm.py" "${_SELECT_ARGS[@]}" \
      || echo "WARN: local LLM setup failed — OpenAI volley fallback remains available."
  else
    # No llmfit: reuse selection.json + weights when present; else default + write selection.
    if [[ "${LOCAL_LLM_REFRESH:-0}" != "1" ]] && python - <<'PY'
from interview_mux.local_llm_selection import selection_cache_valid
raise SystemExit(0 if selection_cache_valid() else 1)
PY
    then
      echo "llmfit not on PATH — reusing cached selection.json + weights."
      echo "  Hardware-aware pick next time: brew install AlexsJones/llmfit/llmfit"
      python "$ROOT/scripts/download_local_llm.py" --verify \
        || echo "WARN: cached MLX verify failed — run with LOCAL_LLM_REFRESH=1 after installing llmfit."
    else
      echo "llmfit not on PATH — downloading default MLX model and writing selection.json."
      echo "  Hardware-aware pick: brew install AlexsJones/llmfit/llmfit"
      MLX_PY="$ROOT/ASSETS/local_llm/venv/bin/python"
      _PY="${MLX_PY}"
      [[ -x "$_PY" ]] || _PY="python"
      if "$_PY" "$ROOT/scripts/download_local_llm.py" \
        --model mlx-community/Llama-3.2-3B-Instruct-4bit --verify; then
        python - <<'PY'
from interview_mux.local_llm_selection import build_fallback_manifest, write_selection_manifest
m = build_fallback_manifest(
    "mlx-community/Llama-3.2-3B-Instruct-4bit",
    reason="llmfit_not_on_path",
)
path = write_selection_manifest(m)
print(f"Wrote fallback selection: {path}")
print(f"  model_id={m.model_id}")
PY
      else
        echo "WARN: local LLM download failed — run: python scripts/select_local_llm.py --download"
      fi
    fi
  fi

  echo "=== Local LLM capability calibration (Stage 1) ==="
  python "$ROOT/scripts/calibrate_local_llm.py" --refresh \
    || echo "WARN: local LLM calibrate failed — degraded LX-01-only capability path remains available."

  python - <<'PY' || true
from interview_mux.local_llm_config import resolve_model_id, resolve_model_path
from interview_mux.local_llm_selection import load_selection_manifest
mid = resolve_model_id()
path = resolve_model_path()
sel = load_selection_manifest() or {}
ctx = sel.get("context_length")
print(f"Active local LLM: {mid}")
if ctx:
    print(f"  context_length={ctx}  source={sel.get('source', '?')}")
print(f"  weights={'ready' if path.is_dir() else 'MISSING'}: {path}")
PY
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
