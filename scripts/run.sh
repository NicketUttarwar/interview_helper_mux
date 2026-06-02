#!/usr/bin/env bash
# Run interview_helper_mux web GUI. Any failure exits the whole process.
# Pass --cli for headless pipeline mode (legacy).
#
# Error output (bootstrap + pipeline) is mirrored to stderr on this terminal when
# MUX_MIRROR_OPERATOR_ERRORS=1 (default). Operator log file: gui_log.jsonl per run.
set -euo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

_CURRENT_STEP="init"

_bash_fatal() {
  local msg="$1"
  local line="${2:-}"
  printf '\n' >&2
  printf '\033[1;31m████████████████████████████████████████████████████████\033[0m\n' >&2
  printf '\033[1;31m██  FATAL — interview_helper_mux run.sh STOPPED         ██\033[0m\n' >&2
  printf '\033[1;31m██  Step: %-44s ██\033[0m\n' "$_CURRENT_STEP" >&2
  if [[ -n "$line" ]]; then
    printf '\033[1;31m██  Line: %-44s ██\033[0m\n' "$line" >&2
  fi
  printf '\033[1;31m██  %-52s ██\033[0m\n' "$msg" >&2
  printf '\033[1;31m████████████████████████████████████████████████████████\033[0m\n' >&2
  printf '\n' >&2
}

_on_err() {
  local exit_code=$?
  _bash_fatal "Command failed (exit ${exit_code})" "${BASH_LINENO[0]:-}"
  exit "${exit_code}"
}

trap _on_err ERR

export PYTHONUNBUFFERED=1
export MUX_LAUNCHED_VIA=run.sh
export MUX_MIRROR_OPERATOR_ERRORS="${MUX_MIRROR_OPERATOR_ERRORS:-1}"

VENV="$ROOT/.venv"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 2>/dev/null || command -v python3)"
fi

_CURRENT_STEP="venv"
if [[ ! -d "$VENV" ]]; then
  echo "Creating virtual environment at .venv ..."
  "$PY" -m venv "$VENV"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

_CURRENT_STEP="pip_install"
pip install -q -U pip setuptools wheel
if [[ -f "$ROOT/requirements.lock" ]]; then
  pip install -q -r "$ROOT/requirements.lock"
else
  pip install -q -r "$ROOT/requirements.txt"
fi
pip install -q "$ROOT"

_CURRENT_STEP="gui_build"
if [[ ! -f "$ROOT/src/interview_mux/web/static/index.html" ]]; then
  echo "Building React GUI (first run or missing static bundle) ..."
  "$ROOT/scripts/build_gui.sh"
fi

if [[ "${1:-}" == "--cli" ]]; then
  shift
  _CURRENT_STEP="cli"
  exec python -m interview_mux "$@"
fi

_CURRENT_STEP="local_llm_check"
if [[ "$(uname -s)" == "Darwin" ]]; then
  "$VENV/bin/python" - <<'PY' || true
from interview_mux.local_llm_config import local_llm_enabled, resolve_model_path
if local_llm_enabled() and not resolve_model_path().is_dir():
    print(
        "Note: local LLM weights missing — run: python scripts/select_local_llm.py --download",
        flush=True,
    )
PY
fi

_CURRENT_STEP="gui_session_reset"
if [[ "${MUX_FRESH_SESSION:-1}" == "1" ]]; then
  GUI_DIR="$("$VENV/bin/python" - <<'PY'
from interview_mux.config import merged_config, repo_root
cfg = merged_config()
print((repo_root() / cfg.get("assets_root", "ASSETS") / ".gui").as_posix())
PY
)"
  echo "Resetting GUI session state for a fresh launch ..."
  rm -f \
    "$GUI_DIR/active_execution.json" \
    "$GUI_DIR/server_session.json" \
    "$GUI_DIR/api_consent.json" \
    "$GUI_DIR/active_execution.json.lock" \
    "$GUI_DIR/server_session.json.lock" \
    "$GUI_DIR/api_consent.json.lock"
fi

_CURRENT_STEP="serve"
exec python -m interview_mux serve "$@"
