#!/usr/bin/env bash
# Run interview_helper_mux web GUI. Any failure exits the whole process.
# Pass --cli for headless pipeline mode (legacy).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PY="${PYTHON:-/opt/homebrew/bin/python3.12}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3.12 2>/dev/null || command -v python3)"
fi

if [[ ! -d "$VENV" ]]; then
  echo "Creating virtual environment at .venv ..."
  "$PY" -m venv "$VENV"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

pip install -q -U pip setuptools wheel
if [[ -f "$ROOT/requirements.lock" ]]; then
  pip install -q -r "$ROOT/requirements.lock"
else
  pip install -q -r "$ROOT/requirements.txt"
fi
pip install -q "$ROOT"

if [[ ! -f "$ROOT/src/interview_mux/web/static/index.html" ]]; then
  echo "Building React GUI (first run or missing static bundle) ..."
  "$ROOT/scripts/build_gui.sh"
fi

if [[ "${1:-}" == "--cli" ]]; then
  shift
  exec python -m interview_mux "$@"
fi

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

exec python -m interview_mux serve "$@"
