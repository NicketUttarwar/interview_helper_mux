#!/usr/bin/env bash
# Verify local stacks after bootstrap (v2: audio + speech + LLM).
# Exit 0 when MMAudio + local speech STT pass on arm64; optional stacks WARN unless STRICT_*=1.
#
# Usage:
#   ./scripts/verify_local_models.sh
#   STRICT_DEEPFILTER=1 ./scripts/verify_local_models.sh
#   STRICT_LOCAL_LLM=1 ./scripts/verify_local_models.sh
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FAIL=0
WARN=0
IS_ARM64=false
if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  IS_ARM64=true
fi

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

echo "Verifying local MLX stacks (v2)..."

if [[ -d .venv ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

DF_PY="$ROOT/ASSETS/local_deepfilter/venv/bin/python"
if [[ ! -x "$DF_PY" ]]; then
  if [[ "${STRICT_DEEPFILTER:-0}" == "1" ]]; then
    _report FAIL "DeepFilterNet" "venv missing — re-run ./scripts/bootstrap_venv.sh (needs Rust for maturin)"
  else
    _report WARN "DeepFilterNet" "venv missing — preclean unavailable; install Rust and re-run bootstrap"
  fi
elif "$DF_PY" "$ROOT/scripts/download_deepfilter.py" --verify >/dev/null 2>&1; then
  _report OK "DeepFilterNet" "venv + df import (optional preclean offer)"
else
  if [[ "${STRICT_DEEPFILTER:-0}" == "1" ]]; then
    _report FAIL "DeepFilterNet" "verify failed — install Rust and re-run ./scripts/bootstrap_venv.sh"
  else
    _report WARN "DeepFilterNet" "not built — preclean offer unavailable"
  fi
fi

MM_PY="$ROOT/ASSETS/local_mmaudio/venv/bin/python"
if [[ ! -x "$MM_PY" ]]; then
  _report FAIL "MMAudio" "venv missing — re-run ./scripts/bootstrap_venv.sh"
elif "$MM_PY" "$ROOT/scripts/download_mmaudio.py" --verify >/dev/null 2>&1; then
  _report OK "MMAudio" "venv + upstream repo (HF weights download on first generation)"
else
  _report FAIL "MMAudio" "verify failed — re-run ./scripts/bootstrap_venv.sh"
fi

SP_PY="$ROOT/ASSETS/local_speech/venv/bin/python"
if [[ ! -x "$SP_PY" ]]; then
  if [[ "$IS_ARM64" == true ]]; then
    _report FAIL "local_speech STT" "venv missing — re-run ./scripts/bootstrap_venv.sh"
  else
    _report WARN "local_speech STT" "skipped (Apple Silicon only)"
  fi
elif "$SP_PY" "$ROOT/scripts/download_local_speech.py" --verify-stt >/dev/null 2>&1; then
  _report OK "local_speech STT" "venv + mlx-audio import"
else
  if [[ "$IS_ARM64" == true ]]; then
    _report FAIL "local_speech STT" "verify failed — re-run ./scripts/bootstrap_venv.sh"
  else
    _report WARN "local_speech STT" "verify failed (non-arm64)"
  fi
fi

if [[ -x "$SP_PY" ]] && "$SP_PY" "$ROOT/scripts/download_local_speech.py" --verify-s2s >/dev/null 2>&1; then
  _report OK "local_speech S2S" "venv + mlx-audio TTS import"
else
  _report WARN "local_speech S2S" "verify failed — G1 synthesize unavailable until fixed"
fi

CB_PY="$ROOT/ASSETS/local_chatterbox/venv/bin/python"
if [[ ! -x "$CB_PY" ]]; then
  if [[ "$IS_ARM64" == true ]]; then
    _report WARN "local_chatterbox" "venv missing — Chatterbox clone unavailable; mlx-audio fallback"
  else
    _report WARN "local_chatterbox" "skipped (Apple Silicon only)"
  fi
elif "$CB_PY" -c "import chatterbox, torch, torchaudio" >/dev/null 2>&1; then
  _report OK "local_chatterbox" "venv + chatterbox import"
  if [[ -x "$CB_PY" ]] && [[ -f "$ROOT/tools/chatterbox_generate.py" ]]; then
    if "$CB_PY" "$ROOT/tools/chatterbox_generate.py" --help >/dev/null 2>&1; then
      _report OK "local_chatterbox CLI" "chatterbox_generate.py reachable"
    else
      _report WARN "local_chatterbox CLI" "generate script unavailable — golden one-liner skipped"
    fi
  fi
else
  _report WARN "local_chatterbox" "verify failed — G1 Chatterbox unavailable; mlx-audio fallback"
fi

LLM_PY="$ROOT/ASSETS/local_llm/venv/bin/python"
if [[ ! -x "$LLM_PY" ]]; then
  if [[ "${STRICT_LOCAL_LLM:-0}" == "1" && "$IS_ARM64" == true ]]; then
    _report FAIL "local_llm framer" "venv missing — re-run ./scripts/bootstrap_venv.sh"
  else
    _report WARN "local_llm framer" "venv missing — volley framer fail-open"
  fi
elif "$LLM_PY" "$ROOT/scripts/download_local_llm.py" --verify >/dev/null 2>&1; then
  _report OK "local_llm framer" "venv + mlx-lm import"
else
  if [[ "${STRICT_LOCAL_LLM:-0}" == "1" && "$IS_ARM64" == true ]]; then
    _report FAIL "local_llm framer" "verify failed — re-run ./scripts/bootstrap_venv.sh"
  else
    _report WARN "local_llm framer" "verify failed — OpenAI-only path continues"
  fi
fi

for entry in "deepfilter:local_deepfilter" "mmaudio:local_mmaudio" "speech:local_speech" "chatterbox:local_chatterbox" "mlx:local_llm"; do
  stack="${entry%%:*}"
  dir="${entry##*:}"
  manifest="$ROOT/ASSETS/${dir}/install.json"
  if [[ ! -f "$manifest" ]]; then
    _report WARN "install.json ($stack)" "missing — re-run ./scripts/bootstrap_venv.sh"
  fi
done

# Golden generate smokes (opt-in): proves real audio out, not just import.
if [[ "${STRICT_LOCAL_SMOKE:-0}" == "1" ]]; then
  echo ""
  echo "Running STRICT_LOCAL_SMOKE golden generates..."
  if [[ -d .venv ]]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
  fi
  if python "$ROOT/tools/smoke_local_runtimes.py" --generate; then
    _report OK "golden_generate" "smoke_local_runtimes.py passed"
  else
    _report FAIL "golden_generate" "smoke_local_runtimes.py failed — see ASSETS/smoke/local_runtimes/"
  fi
else
  _report WARN "golden_generate" "skipped — set STRICT_LOCAL_SMOKE=1 for Chatterbox/S2S/MMAudio/CLAP/DeepFilter generate smokes"
fi

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  if [[ "$WARN" -eq 0 ]]; then
    echo "Local MLX stacks: OK."
  else
    echo "Local MLX stacks: required OK; $WARN optional warning(s)."
  fi
  exit 0
fi

echo "Local MLX stacks: $FAIL required stack(s) failed." >&2
exit 1
