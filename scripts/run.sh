#!/usr/bin/env bash
# Run interview_helper_mux web GUI. Any failure exits the whole process.
#
# Usage:
#   ./scripts/run.sh              # venv + deps + fresh GUI build + serve (default)
#   ./scripts/run.sh --cli …      # headless pipeline mode (legacy)
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

CLI_MODE=0
SERVE_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cli)
      CLI_MODE=1
      shift
      break
      ;;
    -h | --help)
      cat <<'EOF'
Usage: ./scripts/run.sh [options] [serve args…]

  Default: refresh .venv deps, rebuild React GUI, clear session, serve on web_port.

Options:
  --cli             Headless: python -m interview_mux … (no web server)
  -h, --help        Show this help

Environment:
  MUX_PRESERVE_SESSION=1 Keep GUI session pointer across this launch
EOF
      exit 0
      ;;
    *)
      SERVE_ARGS+=("$1")
      shift
      ;;
  esac
done

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
if ! command -v npm >/dev/null 2>&1; then
  _bash_fatal "npm is required to build the GUI. Install Node.js 20+."
  exit 1
fi
echo "Building React GUI (fresh bundle on every launch) ..."
"$ROOT/scripts/build_gui.sh"

if [[ "$CLI_MODE" == "1" ]]; then
  _CURRENT_STEP="cli"
  if (($# > 0)); then
    exec python -m interview_mux "$@"
  else
    exec python -m interview_mux
  fi
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
# Fresh GUI session on every ./scripts/run.sh launch (venv is preserved). Opt out: MUX_PRESERVE_SESSION=1
GUI_DIR="$("$VENV/bin/python" - <<'PY'
from interview_mux.config import merged_config, repo_root
cfg = merged_config()
print((repo_root() / cfg.get("assets_root", "ASSETS") / ".gui").as_posix())
PY
)"
if [[ "${MUX_PRESERVE_SESSION:-0}" == "1" ]]; then
  echo "MUX_PRESERVE_SESSION=1 — keeping GUI session pointer across this launch ..."
  if [[ -f "$GUI_DIR/application_state.json" ]]; then
    ACTIVE_RUN="$("$VENV/bin/python" - <<'PY'
import json
from pathlib import Path
p = Path("""$GUI_DIR/application_state.json""")
try:
    data = json.loads(p.read_text(encoding="utf-8"))
    active = data.get("active") or {}
    print(active.get("run_id") or "")
except Exception:
    print("")
PY
)"
  elif [[ -f "$GUI_DIR/active_execution.json" ]]; then
    ACTIVE_RUN="$("$VENV/bin/python" - <<'PY'
import json
from pathlib import Path
p = Path("""$GUI_DIR/active_execution.json""")
try:
    data = json.loads(p.read_text(encoding="utf-8"))
    print(data.get("run_id") or "")
except Exception:
    print("")
PY
)"
  else
    ACTIVE_RUN=""
  fi
  if [[ -n "$ACTIVE_RUN" ]]; then
    echo "Will restore active execution: ${ACTIVE_RUN}"
  fi
else
  echo "Clearing GUI session state for a fresh Start tab ..."
  rm -f \
    "$GUI_DIR/active_execution.json" \
    "$GUI_DIR/application_state.json" \
    "$GUI_DIR/server_session.json" \
    "$GUI_DIR/api_consent.json" \
    "$GUI_DIR/active_execution.json.lock" \
    "$GUI_DIR/server_session.json.lock" \
    "$GUI_DIR/api_consent.json.lock"
fi

WEB_PORT="$("$VENV/bin/python" - <<'PY'
from interview_mux.config import merged_config
print(int(merged_config().get("web_port", 8765)))
PY
)"

if command -v lsof >/dev/null 2>&1; then
  stale_pids="$(lsof -ti "tcp:${WEB_PORT}" 2>/dev/null || true)"
  if [[ -n "${stale_pids}" ]]; then
    echo "Stopping previous GUI server on port ${WEB_PORT} ..."
    # shellcheck disable=SC2086
    kill ${stale_pids} 2>/dev/null || true
    sleep 1
  fi
fi

_CURRENT_STEP="serve"
if ((${#SERVE_ARGS[@]} > 0)); then
  exec python -m interview_mux serve "${SERVE_ARGS[@]}"
else
  exec python -m interview_mux serve
fi
