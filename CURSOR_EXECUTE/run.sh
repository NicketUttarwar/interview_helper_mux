#!/usr/bin/env bash
# CURSOR_EXECUTE — single entry: ./CURSOR_EXECUTE/run.sh <path-to-commands.md> [cli flags]
set -euo pipefail
IFS=$'\n\t'

EXEC_ROOT="$(cd "$(dirname "$0")" && pwd)"
SESSION_ID="$(date -u +%Y%m%d_%H%M%S)_$$"
LOG_DIR="${EXEC_ROOT}/logs/session_${SESSION_ID}"
TRANSCRIPT="${LOG_DIR}/transcript.log"
PYTHON_EXIT=0
_CURRENT_STEP="init"

_bash_fatal() {
  local msg="$1"
  local line="${2:-}"
  printf '\n' >&2
  printf '\033[1;31m████████████████████████████████████████████████████████\033[0m\n' >&2
  printf '\033[1;31m██  FATAL — CURSOR_EXECUTE run.sh STOPPED              ██\033[0m\n' >&2
  printf '\033[1;31m██  Step: %-44s ██\033[0m\n' "$_CURRENT_STEP" >&2
  if [[ -n "$line" ]]; then
    printf '\033[1;31m██  Line: %-44s ██\033[0m\n' "$line" >&2
  fi
  printf '\033[1;31m██  %-52s ██\033[0m\n' "$msg" >&2
  if [[ -d "${LOG_DIR:-}" ]]; then
    printf '\033[1;31m██  Logs: %-44s ██\033[0m\n' "$LOG_DIR" >&2
    printf '\033[1;31m██  %-52s ██\033[0m\n' "$TRANSCRIPT" >&2
  fi
  printf '\033[1;31m████████████████████████████████████████████████████████\033[0m\n' >&2
  printf '\n' >&2
}

_on_err() {
  local exit_code=$?
  _bash_fatal "Command failed (exit ${exit_code})" "${BASH_LINENO[0]:-}"
  exit "${exit_code}"
}

_on_interrupt() {
  _bash_fatal "Interrupted by user (Ctrl+C)"
  exit 130
}

trap _on_err ERR
trap _on_interrupt INT TERM

if [[ $# -lt 1 ]]; then
  printf 'Usage: %s/run.sh <path-to-commands.md> [cursor-execute flags]\n' "$EXEC_ROOT" >&2
  printf 'Example: %s/run.sh docs/build-out/gap-closure-agent-commands.md --dry-run\n' "$EXEC_ROOT" >&2
  exit 3
fi

MARKDOWN_ARG="$1"
shift

# Resolve markdown path relative to caller cwd
if [[ -f "$MARKDOWN_ARG" ]]; then
  MARKDOWN="$(cd "$(dirname "$MARKDOWN_ARG")" && pwd)/$(basename "$MARKDOWN_ARG")"
else
  _bash_fatal "Markdown file not found: ${MARKDOWN_ARG}"
  exit 3
fi

_CURRENT_STEP="check_api_key"
DRY_RUN=0
for _arg in "$@"; do
  if [[ "$_arg" == "--dry-run" ]]; then
    DRY_RUN=1
    break
  fi
done
if [[ -z "${CURSOR_API_KEY:-}" && "$DRY_RUN" -eq 0 ]]; then
  _bash_fatal "CURSOR_API_KEY is not set. Export it or pass --dry-run"
  exit 3
fi

_CURRENT_STEP="bootstrap_venv"
if [[ ! -x "${EXEC_ROOT}/.venv/bin/python" ]]; then
  printf 'CURSOR_EXECUTE: creating isolated venv...\n'
  bash "${EXEC_ROOT}/bootstrap_venv.sh" || {
    _bash_fatal "bootstrap_venv.sh failed"
    exit 5
  }
fi

# shellcheck source=/dev/null
source "${EXEC_ROOT}/.venv/bin/activate"

_CURRENT_STEP="prepare_logs"
mkdir -p "$LOG_DIR"
export PYTHONUNBUFFERED=1

printf '\n\033[1;36m════════════════════════════════════════════════════════\033[0m\n'
printf '\033[1;36m  CURSOR_EXECUTE — session %s\033[0m\n' "$SESSION_ID"
printf '\033[1;36m  Markdown: %s\033[0m\n' "$MARKDOWN"
printf '\033[1;36m  Logs:     %s\033[0m\n' "$LOG_DIR"
printf '\033[1;36m════════════════════════════════════════════════════════\033[0m\n\n'

_CURRENT_STEP="python_cli"
set +e
python -m cursor_execute.cli "$MARKDOWN" --log-dir "$LOG_DIR" "$@" 2>&1 | tee -a "$TRANSCRIPT"
PYTHON_EXIT=${PIPESTATUS[0]}
set -e

if [[ "$PYTHON_EXIT" -ne 0 ]]; then
  _bash_fatal "Python CLI exited with code ${PYTHON_EXIT}" 
  exit "$PYTHON_EXIT"
fi

printf '\n\033[1;32mCURSOR_EXECUTE finished successfully.\033[0m\n'
printf 'Full transcript: %s\n' "$TRANSCRIPT"
exit 0
