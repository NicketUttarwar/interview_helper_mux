#!/usr/bin/env bash
# Run interview_helper_mux web GUI.
#
# Prerequisite: ./scripts/install.sh  (once per machine / after deleting .venv)
#
# Usage:
#   ./scripts/run.sh              # serve GUI (rebuilds React bundle each launch)
#   ./scripts/run.sh --cli …      # headless pipeline mode
#
# Environment:
#   MUX_PRESERVE_SESSION=1   Keep GUI session pointer across this launch
#   MUX_REFRESH_DEPS=1       Re-run core pip install before serve (after git pull)
#   MUX_SKIP_GUI_BUILD=1     Skip frontend rebuild (use existing static bundle)
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

  Prerequisite: ./scripts/install.sh

  Default: rebuild React GUI (unless MUX_SKIP_GUI_BUILD=1), serve on web_port.

Options:
  --cli             Headless: python -m interview_mux … (no web server)
  -h, --help        Show this help

Environment:
  MUX_PRESERVE_SESSION=1   Keep GUI session across launch
  MUX_REFRESH_DEPS=1     pip install -e ".[dev]" before serve
  MUX_SKIP_GUI_BUILD=1   Use existing GUI static bundle
EOF
      exit 0
      ;;
    *)
      SERVE_ARGS+=("$1")
      shift
      ;;
  esac
done

# shellcheck source=scripts/lib/require_venv.sh
source "$ROOT/scripts/lib/require_venv.sh"
_CURRENT_STEP="venv"
require_core_venv "$ROOT"

VENV="$ROOT/.venv"

if [[ "${MUX_REFRESH_DEPS:-0}" == "1" ]]; then
  _CURRENT_STEP="pip_refresh"
  echo "MUX_REFRESH_DEPS=1 — refreshing core .venv packages ..."
  bash "$ROOT/scripts/lib/install_core_venv.sh"
  # shellcheck source=/dev/null
  source "$VENV/bin/activate"
fi

if [[ "${MUX_SKIP_GUI_BUILD:-0}" != "1" ]]; then
  _CURRENT_STEP="gui_build"
  if ! command -v npm >/dev/null 2>&1; then
    _bash_fatal "npm is required to build the GUI. Install Node.js 20+ or run ./scripts/install.sh"
    exit 1
  fi
  echo "Building React GUI ..."
  bash "$ROOT/scripts/build_gui.sh"
else
  echo "MUX_SKIP_GUI_BUILD=1 — using existing GUI bundle"
fi

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
  python - <<'PY' || true
from interview_mux.local_llm_config import local_llm_enabled, resolve_model_id, resolve_model_path
from interview_mux.local_llm_selection import load_selection_manifest
if not local_llm_enabled():
    raise SystemExit(0)
path = resolve_model_path()
if not path.is_dir():
    print(
        "Note: local LLM weights missing — re-run once: ./scripts/bootstrap_venv.sh",
        flush=True,
    )
else:
    sel = load_selection_manifest() or {}
    mid = resolve_model_id()
    src = sel.get("source") or ("selection.json" if sel else "config default")
    print(f"Local LLM: {mid} ({src})", flush=True)
PY
fi

_CURRENT_STEP="gui_session_reset"
GUI_DIR="$(python - <<'PY'
from interview_mux.config import merged_config, repo_root
cfg = merged_config()
print((repo_root() / cfg.get("assets_root", "ASSETS") / ".gui").as_posix())
PY
)"
if [[ "${MUX_PRESERVE_SESSION:-0}" == "1" ]]; then
  echo "MUX_PRESERVE_SESSION=1 — keeping GUI session pointer across this launch ..."
  if [[ -f "$GUI_DIR/application_state.json" ]]; then
    ACTIVE_RUN="$(python - <<'PY'
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
    ACTIVE_RUN="$(python - <<'PY'
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

WEB_PORT="$(python - <<'PY'
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

_CURRENT_STEP="orphan_workers"
if command -v ps >/dev/null 2>&1; then
  orphan_workers="$(
    ps -ax -o pid=,command= 2>/dev/null \
      | grep 'interview_mux\.stage_worker' \
      | awk '{print $1}' \
      | tr '\n' ' ' \
      || true
  )"
  if [[ -n "${orphan_workers// /}" ]]; then
    echo "Stopping orphan stage worker(s) from a prior session ..."
    # shellcheck disable=SC2086
    kill ${orphan_workers} 2>/dev/null || true
    sleep 1
  fi
fi

_CURRENT_STEP="serve"
if ((${#SERVE_ARGS[@]} > 0)); then
  exec python -m interview_mux serve "${SERVE_ARGS[@]}"
else
  exec python -m interview_mux serve
fi
