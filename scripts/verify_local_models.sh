#!/usr/bin/env bash
# Verify local model stacks after bootstrap (MLX LLM, DeepFilterNet, MMAudio, optional STT).
# Exit 0 when all required stacks pass; 1 when any required stack fails.
#
# Usage:
#   ./scripts/verify_local_models.sh
#   STRICT_LOCAL_STT=1 ./scripts/verify_local_models.sh   # fail if faster-whisper weights missing
#   STRICT_DEEPFILTER=1 ./scripts/verify_local_models.sh # fail if DeepFilterNet stack missing
#
# Docs: SETUP.md § Verify local models
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FAIL=0
WARN=0

_report() {
  local status="$1"
  local name="$2"
  local msg="$3"
  case "$status" in
    OK)   echo "  OK   $name — $msg" ;;
    WARN) echo "  WARN $name — $msg"; WARN=$((WARN + 1)) ;;
    FAIL) echo "  FAIL $name — $msg" >&2; FAIL=$((FAIL + 1)) ;;
  esac
}

echo "Verifying local model stacks..."

if [[ -d .venv ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

# --- MLX LLM (macOS Apple Silicon) ---
if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  MLX_PY="$ROOT/ASSETS/local_llm/venv/bin/python"
  if [[ ! -x "$MLX_PY" ]]; then
    _report FAIL "MLX LLM" "venv missing — re-run ./scripts/bootstrap_venv.sh"
  elif "$MLX_PY" "$ROOT/scripts/download_local_llm.py" --verify >/dev/null 2>&1; then
    _report OK "MLX LLM" "weights loadable (OpenAI fallback if disabled or missing at runtime)"
  else
    _report FAIL "MLX LLM" "run: python scripts/select_local_llm.py --download --verify"
  fi
else
  _report OK "MLX LLM" "skipped (Apple Silicon macOS only; OpenAI volleys used)"
fi

# --- DeepFilterNet (optional preclean) ---
DF_PY="$ROOT/ASSETS/local_deepfilter/venv/bin/python"
if [[ ! -x "$DF_PY" ]]; then
  if [[ "${STRICT_DEEPFILTER:-0}" == "1" ]]; then
    _report FAIL "DeepFilterNet" "venv missing — re-run ./scripts/bootstrap_venv.sh (needs Rust for maturin)"
  else
    _report WARN "DeepFilterNet" "venv missing — preclean unavailable; install Rust and re-run bootstrap"
  fi
elif "$DF_PY" "$ROOT/scripts/download_deepfilter.py" --verify >/dev/null 2>&1; then
  _report OK "DeepFilterNet" "venv + df import (preclean)"
else
  if [[ "${STRICT_DEEPFILTER:-0}" == "1" ]]; then
    _report FAIL "DeepFilterNet" "verify failed — install Rust (brew install rust) and re-run ./scripts/bootstrap_venv.sh"
  else
    _report WARN "DeepFilterNet" "not built — preclean falls back to ffmpeg; install Rust and re-run bootstrap"
  fi
fi

# --- MMAudio (SFX) ---
MM_PY="$ROOT/ASSETS/local_mmaudio/venv/bin/python"
if [[ ! -x "$MM_PY" ]]; then
  _report FAIL "MMAudio" "venv missing — re-run ./scripts/bootstrap_venv.sh"
elif "$MM_PY" "$ROOT/scripts/download_mmaudio.py" --verify >/dev/null 2>&1; then
  _report OK "MMAudio" "venv + upstream repo (HF weights download on first generation)"
else
  _report FAIL "MMAudio" "verify failed — re-run ./scripts/bootstrap_venv.sh"
fi

# --- faster-whisper (disfluency_extract; optional) ---
STT_PY="${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}"
STT_PY="${STT_PY:-python}"
if "$STT_PY" "$ROOT/scripts/download_local_stt.py" --verify >/dev/null 2>&1; then
  _report OK "faster-whisper (STT)" "weights cached under ASSETS/local_stt/models"
elif [[ "${STRICT_LOCAL_STT:-0}" == "1" ]]; then
  _report FAIL "faster-whisper (STT)" "run: python scripts/download_local_stt.py --model base"
else
  _report WARN "faster-whisper (STT)" "optional — lexicon pass works without weights; run: python scripts/download_local_stt.py --model base"
fi

# --- install.json manifests (informational) ---
for entry in "mlx:local_llm" "deepfilter:local_deepfilter" "mmaudio:local_mmaudio"; do
  stack="${entry%%:*}"
  dir="${entry##*:}"
  manifest="$ROOT/ASSETS/${dir}/install.json"
  if [[ ! -f "$manifest" ]]; then
    _report WARN "install.json ($stack)" "missing — re-run ./scripts/bootstrap_venv.sh"
  fi
done

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  if [[ "$WARN" -eq 0 ]]; then
    echo "Local models: all stacks OK."
  else
    echo "Local models: required stacks OK; $WARN optional warning(s)."
  fi
  exit 0
fi

echo "Local models: $FAIL required stack(s) failed — see SETUP.md § Verify local models." >&2
exit 1
