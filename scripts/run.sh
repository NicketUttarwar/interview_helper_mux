#!/usr/bin/env bash
# Start the web GUI (default) or headless CLI.
#
# First time on this machine:
#   ./scripts/bootstrap_venv.sh
#   ./scripts/run.sh
#
# Options:
#   ./scripts/run.sh --cli …     python -m interview_mux … (no server)
#   MUX_PRESERVE_SESSION=1       Keep last run selected in the GUI
#   MUX_REBUILD_GUI=1            Rebuild React bundle before serve
#   MUX_REFRESH_DEPS=1           Re-pip core .venv after git pull
set -euo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONUNBUFFERED=1
export MUX_LAUNCHED_VIA=run.sh

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
Usage: ./scripts/run.sh [--cli] [serve args…]

Setup once:  ./scripts/bootstrap_venv.sh
Launch:      ./scripts/run.sh

Environment:
  MUX_PRESERVE_SESSION=1   Keep GUI session across launches
  MUX_REBUILD_GUI=1        npm build before serve
  MUX_REFRESH_DEPS=1       Refresh core .venv after git pull
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
require_core_venv "$ROOT"

if [[ "${MUX_REFRESH_DEPS:-0}" == "1" ]]; then
  bash "$ROOT/scripts/lib/install_core_venv.sh"
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"
fi

if [[ "${MUX_REBUILD_GUI:-0}" == "1" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm required for MUX_REBUILD_GUI=1 — install Node.js 20+" >&2
    exit 1
  fi
  bash "$ROOT/scripts/build_gui.sh"
elif [[ ! -f "$ROOT/src/interview_mux/web/static/index.html" ]]; then
  echo "ERROR: GUI bundle missing — run ./scripts/bootstrap_venv.sh first" >&2
  exit 1
fi

if [[ "$CLI_MODE" == "1" ]]; then
  if (($# > 0)); then
    exec python -m interview_mux "$@"
  fi
  exec python -m interview_mux
fi

GUI_DIR="$(python - <<'PY'
from interview_mux.config import merged_config, repo_root
print((repo_root() / merged_config().get("assets_root", "ASSETS") / ".gui").as_posix())
PY
)"

if [[ "${MUX_PRESERVE_SESSION:-0}" != "1" ]]; then
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
    kill ${stale_pids} 2>/dev/null || true
    sleep 1
  fi
fi

if command -v ps >/dev/null 2>&1; then
  orphan_workers="$(ps -ax -o pid=,command= 2>/dev/null | grep 'interview_mux\.stage_worker' | awk '{print $1}' | tr '\n' ' ' || true)"
  if [[ -n "${orphan_workers// /}" ]]; then
    kill ${orphan_workers} 2>/dev/null || true
    sleep 1
  fi
fi

if ((${#SERVE_ARGS[@]} > 0)); then
  exec python -m interview_mux serve "${SERVE_ARGS[@]}"
fi
exec python -m interview_mux serve
