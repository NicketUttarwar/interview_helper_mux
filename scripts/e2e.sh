#!/usr/bin/env bash
# Autonomous full-application E2E runner — repo root entry point.
# Prepare → Ship for flow1, flow2, and flow3 using ASSETS/input/interview.wav.
# Implementation: tests/e2e/
set -euo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
E2E_ROOT="${ROOT}/tests/e2e"
SESSION_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="${E2E_ROOT}/logs/session_${SESSION_ID}"
REPO_VENV="${ROOT}/.venv"
E2E_VENV="${E2E_ROOT}/.venv"
REPO_PYTHON="${REPO_VENV}/bin/python"
E2E_PYTHON="${E2E_VENV}/bin/python"
DEFAULT_INPUT="ASSETS/input/interview.wav"
DEFAULT_FLOWS="flow1,flow2,flow3"

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

_step() {
  printf '\n--- %s ---\n' "$1"
}

_has_flag() {
  local flag="$1"
  shift
  for arg in "$@"; do
    if [[ "$arg" == "$flag" ]]; then
      return 0
    fi
  done
  return 1
}

_step "E2E tier 0: input audio"
if [[ ! -f "${ROOT}/${DEFAULT_INPUT}" ]]; then
  _bash_fatal "Missing ${DEFAULT_INPUT} — see SETUP.md §3 Media"
  exit 1
fi
echo "Input: ${DEFAULT_INPUT}"

_step "E2E tier 1: repo .venv"
if [[ ! -x "${REPO_PYTHON}" ]]; then
  echo "Creating repo .venv (scripts/bootstrap_venv.sh)..."
  bash "${ROOT}/scripts/bootstrap_venv.sh"
fi
if [[ ! -x "${REPO_PYTHON}" ]]; then
  _bash_fatal "Repo .venv missing at ${REPO_VENV} — run ./scripts/bootstrap_venv.sh"
  exit 1
fi
echo "Repo Python: ${REPO_PYTHON}"

_step "E2E tier 2: E2E venv (Playwright + cursor-sdk)"
if [[ ! -x "${E2E_PYTHON}" ]]; then
  echo "Creating tests/e2e/.venv..."
  bash "${E2E_ROOT}/bootstrap_venv.sh"
fi
"${E2E_PYTHON}" -m pip install -q -e "${E2E_ROOT}"
echo "E2E Python: ${E2E_PYTHON}"

_step "E2E tier 3: GUI static bundle"
if [[ ! -f "${ROOT}/src/interview_mux/web/static/index.html" ]]; then
  echo "Building React GUI (first run)..."
  bash "${ROOT}/scripts/build_gui.sh"
else
  echo "GUI static bundle present"
fi

_step "E2E tier 4: prerequisites and secrets"
"${ROOT}/tools/check_prerequisites.sh"

SECRETS_FILE="${ROOT}/config/secrets/secrets.env"
if [[ ! -f "${SECRETS_FILE}" ]]; then
  _bash_fatal "Missing ${SECRETS_FILE} — cp config/templates/secrets.env.example config/secrets/secrets.env"
  exit 1
fi

"${REPO_PYTHON}" - <<'PY'
import sys
from interview_mux.config import merged_config

secrets = merged_config().get("secrets") or {}
required = ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "AWS_S3_BUCKET")
missing = [k for k in required if not str(secrets.get(k) or "").strip()]
if missing:
    print(
        "E2E FATAL: missing secrets in config/secrets/secrets.env: "
        + ", ".join(missing),
        file=sys.stderr,
    )
    sys.exit(1)
print("Secrets: required API keys present")
PY

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  _bash_fatal "AWS credentials not valid — run aws configure or aws sso login"
  exit 1
fi
echo "AWS: sts get-caller-identity OK"

_step "E2E tier 5: config import smoke"
"${REPO_PYTHON}" -c "from interview_mux.config import merged_config; merged_config()"
echo "Config import: OK"

_step "E2E tier 6: E2E helper unit tests"
"${REPO_PYTHON}" -m pytest "${ROOT}/tests/e2e/" -q \
  --ignore="${ROOT}/tests/e2e/test_live.py" \
  -k "not live"

mkdir -p "$LOG_DIR"
export PYTHONUNBUFFERED=1
export PATH="${E2E_VENV}/bin:${PATH}"

no_heal=0
if _has_flag --no-heal "$@"; then
  no_heal=1
fi

if [[ "$no_heal" -eq 0 ]]; then
  has_cursor_key="$("${E2E_PYTHON}" -c "
from pathlib import Path
import sys
sys.path.insert(0, '${E2E_ROOT}')
from e2e_runner.secrets import cursor_api_key
print('yes' if cursor_api_key(Path('${ROOT}')) else 'no')
")"
  if [[ "$has_cursor_key" != "yes" ]]; then
    echo "Note: CURSOR_API_KEY not set in config/secrets/secrets.env — heal will skip agent fixes (use --no-heal to silence)"
  fi
fi

E2E_ARGS=(--log-dir "$LOG_DIR")
if ! _has_flag --input "$@" && ! _has_flag --resume-run-id "$@"; then
  E2E_ARGS+=(--input "$DEFAULT_INPUT")
fi
if ! _has_flag --flows "$@"; then
  E2E_ARGS+=(--flows "$DEFAULT_FLOWS")
fi
E2E_ARGS+=("$@")

_step "E2E tier 7: live journey (${DEFAULT_FLOWS})"
echo "Log dir: ${LOG_DIR}"
"${E2E_PYTHON}" -m e2e_runner "${E2E_ARGS[@]}"
EXIT=$?

REPORT="${E2E_ROOT}/reports/${SESSION_ID}_final-report.md"
if [[ -f "$REPORT" ]]; then
  echo ""
  echo "Final report: $REPORT"
fi
echo "Session logs: $LOG_DIR"

exit "$EXIT"
