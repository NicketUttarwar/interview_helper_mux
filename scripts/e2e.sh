#!/usr/bin/env bash
# Autonomous full-application E2E runner — repo root entry point.
set -euo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
E2E_ROOT="${ROOT}/E2E_RUN"
SESSION_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="${E2E_ROOT}/logs/session_${SESSION_ID}"

_bash_fatal() {
  local msg="$1"
  printf '\n\033[1;31mE2E FATAL: %s\033[0m\n' "$msg" >&2
  if [[ -d "${LOG_DIR}" ]]; then
    printf 'Logs: %s\n' "$LOG_DIR" >&2
  fi
}

_on_err() {
  _bash_fatal "Command failed (exit $?)"
  exit 1
}

trap _on_err ERR

if [[ ! -f "${ROOT}/ASSETS/input/interview.wav" ]]; then
  _bash_fatal "Missing ASSETS/input/interview.wav — see SETUP.md §3 Media"
  exit 1
fi

"${ROOT}/tools/check_prerequisites.sh"

if [[ ! -x "${E2E_ROOT}/.venv/bin/python" ]]; then
  echo "E2E_RUN: creating isolated venv..."
  bash "${E2E_ROOT}/bootstrap_venv.sh"
fi

# shellcheck source=/dev/null
source "${E2E_ROOT}/.venv/bin/activate"

if [[ -d "${ROOT}/.venv" ]]; then
  # shellcheck source=/dev/null
  source "${ROOT}/.venv/bin/activate"
  pytest "${ROOT}/tests/" -q \
    --ignore="${ROOT}/tests/test_e2e_live.py" \
    -k "not e2e_live" \
    || true
fi

mkdir -p "$LOG_DIR"
export PYTHONUNBUFFERED=1

HEAL_FLAG=()
for arg in "$@"; do
  if [[ "$arg" == "--no-heal" ]]; then
    HEAL_FLAG=(--no-heal)
  fi
done

if [[ -z "${CURSOR_API_KEY:-}" && "${HEAL_FLAG[*]}" != *no-heal* ]]; then
  echo "Note: CURSOR_API_KEY unset — heal will skip agent fixes (use --no-heal to silence)"
fi

python -m e2e_runner run --log-dir "$LOG_DIR" "$@"
EXIT=$?

REPORT="${ROOT}/docs/e2e-reports/${SESSION_ID}_final-report.md"
if [[ -f "$REPORT" ]]; then
  echo ""
  echo "Final report: $REPORT"
fi
echo "Session logs: $LOG_DIR"

exit "$EXIT"
