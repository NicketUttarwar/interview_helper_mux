#!/usr/bin/env bash
# Flow 1 GUI E2E — single entry: preflight → server → Playwright driver ↔ fix loop → finish
#
#   ./CURSOR_EXECUTE/flow1-gui-e2e/run.sh
#   ./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --config driver/config.tbiy.yaml
#
# Ctrl+C stops automation safely (exit 130) and saves driver/state.json for --resume.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/lib/secrets_env.sh"
load_secrets_env "${REPO_ROOT}"
CAMPAIGN_DIR="${SCRIPT_DIR}"
DRIVER_DIR="${CAMPAIGN_DIR}/driver"
EXEC_RUN="${REPO_ROOT}/CURSOR_EXECUTE/run.sh"
COMMANDS_MD="${CAMPAIGN_DIR}/agent-commands.md"
CONFIG_REL="driver/config.yaml"
DRIVER_CONFIG=""
INPUT_WAV="${REPO_ROOT}/ASSETS/notebooklm_original_interview_2024.wav"
ONE_LINER="cd ${REPO_ROOT} && ./CURSOR_EXECUTE/flow1-gui-e2e/run.sh"

SESSION_DIR=""
SERVER_PID=""
DRIVER_PID=""
SERVER_LOG=""
_TRANSCRIPT=""
_DRIVER_PY="${REPO_ROOT}/CURSOR_EXECUTE/.venv/bin/python"
SCREENSHOT_ARCHIVE="${REPO_ROOT}/ASSETS/flow1-gui-e2e-screenshots"

# ── logging ─────────────────────────────────────────────────────────────

_ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

_init_session() {
  SESSION_DIR="${CAMPAIGN_DIR}/logs/session_$(date -u +%Y%m%dT%H%M%S)_$$"
  mkdir -p "${SESSION_DIR}/screenshots"
  SERVER_LOG="${SESSION_DIR}/server.log"
  _TRANSCRIPT="${SESSION_DIR}/transcript.log"
  touch "${_TRANSCRIPT}"
}

_log_line() {
  local prefix="$1"
  local msg="$2"
  local color="${3:-}"
  local reset="\033[0m"
  local line="$(_ts) | ${prefix} | ${msg}"
  if [[ -n "${color}" ]]; then
    printf '%b%s%b\n' "${color}" "${line}" "${reset}"
  else
    printf '%s\n' "${line}"
  fi
  if [[ -n "${_TRANSCRIPT:-}" ]]; then
    printf '%s\n' "${line}" >> "${_TRANSCRIPT}"
  fi
}

_log_step() {
  local phase="$1"
  local msg="$2"
  _log_line "STEP" "[${phase}] ${msg}" "\033[1;36m"
}

_log_action() {
  _log_line "ACTION" "$1" "\033[1;32m"
}

_log_wait() {
  _log_line "WAIT" "$1" "\033[1;33m"
}

_log_info() {
  _log_line "INFO" "$1"
}

_log_blocker() {
  _log_line "BLOCKER" "$1" "\033[1;31m"
}

_log_fatal() {
  _log_line "FATAL" "$1" "\033[1;31m"
}

_print_banner() {
  printf '\n\033[1;36m════════════════════════════════════════════════════════\033[0m\n'
  printf '\033[1;36m  Flow 1 GUI E2E — automated run\033[0m\n'
  printf '\033[1;36m  Repo:    %s\033[0m\n' "${REPO_ROOT}"
  printf '\033[1;36m  Config:  %s\033[0m\n' "${CONFIG_REL}"
  printf '\033[1;36m  Input:   %s\033[0m\n' "${INPUT_WAV#${REPO_ROOT}/}"
  printf '\033[1;36m  Kill:    Ctrl+C saves state for --resume\033[0m\n'
  printf '\033[1;36m════════════════════════════════════════════════════════\033[0m\n\n'
}

# ── cleanup on Ctrl+C ───────────────────────────────────────────────────

_cleanup() {
  local sig="${1:-}"
  printf '\n'
  _log_blocker "Automation stopped by operator (signal ${sig:-INT}). Saving state…"
  if [[ -n "${DRIVER_PID:-}" ]] && kill -0 "${DRIVER_PID}" 2>/dev/null; then
    kill "${DRIVER_PID}" 2>/dev/null || true
    wait "${DRIVER_PID}" 2>/dev/null || true
  fi
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    _log_step "SERVER" "Stopping GUI server (pid ${SERVER_PID})"
    kill -- -"${SERVER_PID}" 2>/dev/null || kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  _phase_screenshot_archive_finalize
  _log_info "Resume: ${ONE_LINER} --resume"
  exit 130
}

trap '_cleanup INT' INT
trap '_cleanup TERM' TERM

# ── flags ─────────────────────────────────────────────────────────────────

DRY_RUN=0
RESUME=0
NO_FIX=0
HEADED=0
VERBOSE=0
MAX_FIX_ROUNDS=10
FROM_STEP=1
TO_STEP=4

_resolve_driver_config() {
  if [[ "${CONFIG_REL}" = /* ]]; then
    DRIVER_CONFIG="${CONFIG_REL}"
  else
    DRIVER_CONFIG="${CAMPAIGN_DIR}/${CONFIG_REL}"
  fi
  if [[ ! -f "${DRIVER_CONFIG}" ]]; then
    _log_fatal "Missing driver config: ${DRIVER_CONFIG}"
    exit 1
  fi
  local wav_rel
  wav_rel="$(grep -E '^input_wav:' "${DRIVER_CONFIG}" | head -1 | sed 's/^input_wav:[[:space:]]*//')"
  if [[ -n "${wav_rel}" ]]; then
    INPUT_WAV="${REPO_ROOT}/${wav_rel}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --resume) RESUME=1 ;;
    --no-fix) NO_FIX=1 ;;
    --headed) HEADED=1 ;;
    --verbose) VERBOSE=1 ;;
    --config) CONFIG_REL="$2"; shift ;;
    --from) FROM_STEP="$2"; shift ;;
    --to) TO_STEP="$2"; shift ;;
    --max-fix-rounds) MAX_FIX_ROUNDS="$2"; shift ;;
    -h|--help)
      sed -n '2,22p' "$0"
      exit 0
      ;;
    *) _log_fatal "Unknown flag: $1"; exit 1 ;;
  esac
  shift
done

_resolve_driver_config

# ── phases ────────────────────────────────────────────────────────────────

_phase_setup() {
  _log_step "SETUP" "Preflight checks"
  if [[ ! -f "${INPUT_WAV}" ]]; then
    _log_fatal "Missing input WAV: ${INPUT_WAV}"
    exit 1
  fi
  _log_info "PASS input WAV exists"

  if [[ ! -f "${REPO_ROOT}/config/secrets/secrets.env" ]]; then
    _log_fatal "Missing config/secrets/secrets.env"
    exit 1
  fi
  _log_info "PASS secrets.env exists"

  if command -v ffmpeg >/dev/null 2>&1; then
    _log_info "PASS ffmpeg"
  else
    _log_fatal "ffmpeg not found"
    exit 1
  fi

  _log_step "SETUP" "Bootstrap CURSOR_EXECUTE venv + playwright"
  "${REPO_ROOT}/CURSOR_EXECUTE/bootstrap_venv.sh"
  # shellcheck source=/dev/null
  source "${REPO_ROOT}/CURSOR_EXECUTE/.venv/bin/activate"
  pip install -q -e "${REPO_ROOT}/CURSOR_EXECUTE/.[e2e]" 2>/dev/null || pip install -q -r "${DRIVER_DIR}/requirements.txt"
  playwright install chromium 2>/dev/null || true
  _log_info "PASS playwright ready"

  _log_step "SETUP" "Generate dummy VO fixture"
  chmod +x "${CAMPAIGN_DIR}/fixtures/generate_dummy_vo.sh"
  "${CAMPAIGN_DIR}/fixtures/generate_dummy_vo.sh"
  _log_info "PASS fixtures/dummy_vo.wav"

  if [[ -x "${REPO_ROOT}/tools/check_prerequisites.sh" ]]; then
    _log_step "SETUP" "Running check_prerequisites.sh"
    if "${REPO_ROOT}/tools/check_prerequisites.sh"; then
      _log_info "PASS check_prerequisites"
    else
      _log_blocker "check_prerequisites failed — fix before full run"
    fi
  fi

  _log_step "SETUP" "Ensure GUI bundle includes E2E testids"
  if ! command -v npm >/dev/null 2>&1; then
    _log_fatal "npm required to build GUI for E2E — install Node.js 20+ (see SETUP.md)"
    exit 1
  fi
  _e2e_gui_has_markers() {
    local js
    for js in "${REPO_ROOT}/src/interview_mux/web/static/assets/index-"*.js; do
      [[ -f "$js" ]] || continue
      grep -q 'start-tab-ready' "$js" && return 0
    done
    return 1
  }
  if ! _e2e_gui_has_markers; then
    _log_info "GUI bundle stale — running ./scripts/build_gui.sh"
    "${REPO_ROOT}/scripts/build_gui.sh"
    if ! _e2e_gui_has_markers; then
      _log_fatal "GUI rebuild did not produce start-tab-ready — check frontend build"
      exit 1
    fi
    _log_info "PASS GUI rebuilt with E2E markers"
  else
    _log_info "PASS GUI bundle contains E2E markers"
  fi

  _log_step "SETUP" "Complete"
}

_phase_server() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    _log_step "SERVER" "Skipped (dry-run)"
    return 0
  fi
  local port=8765
  if [[ -f "${REPO_ROOT}/config/app.defaults.json" ]]; then
    port="$(python3 -c "import json; print(json.load(open('${REPO_ROOT}/config/app.defaults.json')).get('web_port',8765))" 2>/dev/null || echo 8765)"
  fi
  if command -v lsof >/dev/null 2>&1; then
    local stale_pids=""
    stale_pids="$(lsof -ti "tcp:${port}" 2>/dev/null || true)"
    if [[ -n "${stale_pids}" ]]; then
      _log_wait "Port ${port} in use — stopping stale listener(s): ${stale_pids}"
      # shellcheck disable=SC2086
      kill ${stale_pids} 2>/dev/null || true
      sleep 2
    fi
  fi

  _log_step "SERVER" "Starting ./scripts/run.sh (fresh session by default)"
  (
    cd "${REPO_ROOT}"
    ./scripts/run.sh
  ) >> "${SERVER_LOG}" 2>&1 &
  SERVER_PID=$!
  _log_info "Server pid=${SERVER_PID} log=${SERVER_LOG}"

  local attempt=0
  local max=60
  while [[ "${attempt}" -lt "${max}" ]]; do
    attempt=$((attempt + 1))
    if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
      _log_fatal "Server process exited before health check (see ${SERVER_LOG})"
      tail -n 30 "${SERVER_LOG}" >&2 || true
      exit 1
    fi
    if curl -sf "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1; then
      if grep -q "address already in use" "${SERVER_LOG}" 2>/dev/null; then
        _log_fatal "Server failed to bind ${port} — stale process may still own the port"
        tail -n 30 "${SERVER_LOG}" >&2 || true
        exit 1
      fi
      _log_info "PASS /api/health (attempt ${attempt})"
      return 0
    fi
    _log_wait "Waiting for server health (${attempt}/${max})"
    sleep 2
  done
  _log_fatal "Server not healthy after ${max} attempts"
  tail -n 30 "${SERVER_LOG}" >&2 || true
  exit 1
}

_phase_driver() {
  if [[ ! -x "${_DRIVER_PY}" ]]; then
    _log_fatal "CURSOR_EXECUTE venv missing — run without --from 2 or run SETUP first"
    exit 1
  fi
  local driver_args=("${_DRIVER_PY}" "${DRIVER_DIR}/gui_driver.py" --session-dir "${SESSION_DIR}")
  driver_args+=(--config "${DRIVER_CONFIG}")
  [[ "${RESUME}" -eq 1 ]] && driver_args+=(--resume)
  [[ "${DRY_RUN}" -eq 1 ]] && driver_args+=(--dry-run)
  [[ "${HEADED}" -eq 1 ]] && driver_args+=(--headed)
  [[ "${VERBOSE}" -eq 1 ]] && driver_args+=(--verbose)

  _log_step "DRIVER" "Launching Playwright driver"
  _log_action "Command: ${driver_args[*]}"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    (cd "${DRIVER_DIR}" && "${driver_args[@]}") 2>&1 | tee -a "${_TRANSCRIPT}"
    return 0
  fi

  (cd "${DRIVER_DIR}" && "${driver_args[@]}") 2>&1 | tee -a "${_TRANSCRIPT}"
  return "${PIPESTATUS[0]}"
}

_phase_fix() {
  local blocker
  blocker="$(ls -t "${CAMPAIGN_DIR}"/blockers/BLOCKER-*.md 2>/dev/null | head -1 || true)"
  if [[ -z "${blocker}" ]]; then
    _log_blocker "No blocker file found for fix phase"
    return 1
  fi
  _log_blocker "Latest blocker: ${blocker}"
  if [[ "${NO_FIX}" -eq 1 ]]; then
    _log_info "Skipping E2E-03 (--no-fix)"
    return 1
  fi
  if [[ ! -x "${EXEC_RUN}" ]]; then
    _log_fatal "CURSOR_EXECUTE/run.sh not found"
    return 1
  fi
  _log_step "FIX" "Invoking CURSOR_EXECUTE E2E-03"
  if ! require_secrets_env_key "CURSOR_API_KEY" "${REPO_ROOT}"; then
    _log_blocker "CURSOR_API_KEY not set — fix blocker manually then --resume"
    return 1
  fi
  "${EXEC_RUN}" "${COMMANDS_MD}" --from 3 --to 3 || return 1
  if git -C "${REPO_ROOT}" diff --name-only -- frontend/ 2>/dev/null | grep -q .; then
    _log_step "REBUILD" "frontend changed — building GUI"
    "${REPO_ROOT}/scripts/build_gui.sh"
  fi
  return 0
}

_phase_commit_fix() {
  local blocker
  blocker="$(ls -t "${CAMPAIGN_DIR}"/blockers/BLOCKER-*.md 2>/dev/null | head -1 || true)"
  if ! git -C "${REPO_ROOT}" diff --name-only 2>/dev/null | grep -q .; then
    _log_info "No repo changes to commit after fix"
    return 0
  fi
  _log_step "COMMIT" "Staging fix from ${blocker:-blocker}"
  git -C "${REPO_ROOT}" add -A
  local slug="e2e-blocker-fix"
  [[ -n "${blocker}" ]] && slug="$(basename "${blocker}" .md | tr '[:upper:]' '[:lower:]')"
  if git -C "${REPO_ROOT}" commit -m "$(cat <<EOF
fix(e2e): ${slug}

Automated fix after Flow 1 GUI E2E blocker.
EOF
)"; then
    _log_info "PASS git commit for blocker fix"
    _log_step "PUSH" "git push origin main"
    if git -C "${REPO_ROOT}" push origin main; then
      _log_info "PASS git push origin main"
    else
      _log_blocker "git push origin main failed — fix is committed locally only"
      return 1
    fi
  else
    _log_info "Nothing to commit (working tree unchanged after add)"
  fi
}

_print_blocker_summary() {
  local outcome="$1"
  local blocker run_id symptom
  blocker="$(ls -t "${CAMPAIGN_DIR}"/blockers/BLOCKER-*.md 2>/dev/null | head -1 || true)"
  run_id=""
  symptom=""
  if [[ -f "${DRIVER_DIR}/state.json" ]]; then
    run_id="$(python3 -c "import json; print(json.load(open('${DRIVER_DIR}/state.json')).get('run_id') or '')" 2>/dev/null || true)"
  fi
  if [[ -n "${blocker}" ]]; then
    symptom="$(awk '/^## Symptom$/{f=1;next} f&&/^## /{exit} f' "${blocker}" | sed '/^$/d' | head -3 | tr '\n' ' ')"
  fi
  printf '\n'
  printf '\033[1;33m════════════════════════════════════════════════════════\033[0m\n'
  printf '\033[1;33m  Flow 1 GUI E2E — BLOCKER SUMMARY\033[0m\n'
  printf '\033[1;33m════════════════════════════════════════════════════════\033[0m\n'
  printf '  Outcome:    %s\n' "${outcome}"
  [[ -n "${blocker}" ]] && printf '  Blocker:    %s\n' "${blocker}"
  [[ -n "${run_id}" ]] && printf '  run_id:     %s\n' "${run_id}"
  [[ -n "${symptom}" ]] && printf '  Symptom:    %s\n' "${symptom}"
  printf '  Session:    %s\n' "${SESSION_DIR}"
  printf '\n'
  printf '  The driver stopped instead of retrying forever.\n'
  printf '  Review the blocker file and session log, then rerun:\n'
  printf '\n'
  printf '    %s --resume\n' "${ONE_LINER}"
  printf '\n'
  printf '\033[1;33m════════════════════════════════════════════════════════\033[0m\n\n'
}

_phase_finish() {
  _log_step "FINISH" "Verification"
  local state_file="${DRIVER_DIR}/state.json"
  local run_id=""
  if [[ -f "${state_file}" ]]; then
    run_id="$(python3 -c "import json; print(json.load(open('${state_file}')).get('run_id') or '')" 2>/dev/null || true)"
  fi
  if [[ -z "${run_id}" ]]; then
    _log_blocker "No run_id in driver/state.json — skip verify"
    return 0
  fi
  local master="${REPO_ROOT}/ASSETS/executions/${run_id}/flow_1_master/master.wav"
  if [[ ! -f "${master}" ]]; then
    _log_blocker "master.wav not found: ${master}"
    return 1
  fi
  _log_info "Found ${master}"
  if [[ -d "${REPO_ROOT}/.venv" ]]; then
    # shellcheck source=/dev/null
    source "${REPO_ROOT}/.venv/bin/activate"
    _log_step "FINISH" "verify_master.py"
    python "${REPO_ROOT}/tools/verify_master.py" "${master}" && _log_info "PASS verify_master"
    _log_step "FINISH" "validate_narrative.py"
    python "${REPO_ROOT}/tools/validate_narrative.py" --run-id "${run_id}" --include-edl && _log_info "PASS validate_narrative"
  fi
  _log_step "FINISH" "Complete for ${run_id}"
}

_phase_screenshot_archive_finalize() {
  if [[ "${DRY_RUN:-0}" -eq 1 ]]; then
    return 0
  fi
  if [[ ! -d "${SCREENSHOT_ARCHIVE}/.git" ]]; then
    return 0
  fi
  _log_step "SCREENSHOTS" "Finalizing execution screenshot archive"
  _log_info "Archive path: ${SCREENSHOT_ARCHIVE}"
  if git -C "${SCREENSHOT_ARCHIVE}" status --porcelain 2>/dev/null | grep -q .; then
    git -C "${SCREENSHOT_ARCHIVE}" add -A
    local sess_name=""
    [[ -n "${SESSION_DIR:-}" ]] && sess_name="$(basename "${SESSION_DIR}")"
    git -C "${SCREENSHOT_ARCHIVE}" commit -m "e2e run.sh finalize ${sess_name:-session}" 2>/dev/null \
      && _log_info "PASS screenshot archive git commit" \
      || _log_info "Screenshot archive: nothing new to commit (driver may have committed already)"
  else
    _log_info "Screenshot archive: clean working tree"
  fi
  local count=0
  if [[ -n "${SESSION_DIR:-}" && -d "${SCREENSHOT_ARCHIVE}/sessions/$(basename "${SESSION_DIR}")" ]]; then
    count="$(find "${SCREENSHOT_ARCHIVE}/sessions/$(basename "${SESSION_DIR}")" -name '*.png' 2>/dev/null | wc -l | tr -d ' ')"
  fi
  _log_info "Session PNG count in archive: ${count} (max 1 capture per 2 min per button click)"
}

# ── main ──────────────────────────────────────────────────────────────────

main() {
  _init_session
  _print_banner

  if [[ "${FROM_STEP}" -le 1 && "${TO_STEP}" -ge 1 ]]; then
    _phase_setup
  fi

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    _phase_driver
    _log_step "DRY-RUN" "Complete — no server started"
    exit 0
  fi

  if [[ "${FROM_STEP}" -le 2 && "${TO_STEP}" -ge 2 ]]; then
    if [[ "${RESUME}" -eq 0 ]]; then
      _phase_server
    else
      _log_step "SERVER" "Resume — assuming server already running"
    fi
  fi

  local fix_round=0
  while [[ "${fix_round}" -le "${MAX_FIX_ROUNDS}" ]]; do
    if [[ "${FROM_STEP}" -le 3 && "${TO_STEP}" -ge 3 ]]; then
      set +e
      _phase_driver
      local drv_exit=$?
      set -e
      if [[ "${drv_exit}" -eq 0 ]]; then
        break
      fi
      if [[ "${drv_exit}" -ne 2 ]]; then
        _log_fatal "Driver exited with code ${drv_exit}"
        exit "${drv_exit}"
      fi
      fix_round=$((fix_round + 1))
      if [[ "${fix_round}" -gt "${MAX_FIX_ROUNDS}" ]]; then
        _print_blocker_summary "max_fix_rounds_exceeded"
        _log_fatal "Max fix rounds (${MAX_FIX_ROUNDS}) exceeded"
        exit 1
      fi
      if [[ "${NO_FIX}" -eq 1 ]]; then
        _print_blocker_summary "blocker_no_fix"
        exit 2
      fi
      if ! _phase_fix; then
        _print_blocker_summary "fix_failed"
        exit 1
      fi
      _phase_commit_fix
      if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
        _log_step "SERVER" "Stopping GUI server after fix"
        kill -- -"${SERVER_PID}" 2>/dev/null || kill "${SERVER_PID}" 2>/dev/null || true
      fi
      _phase_screenshot_archive_finalize
      _print_blocker_summary "fix_applied"
      exit 0
    else
      break
    fi
  done

  if [[ "${FROM_STEP}" -le 4 && "${TO_STEP}" -ge 4 ]]; then
    _phase_finish
  fi

  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    _log_step "SERVER" "Stopping GUI server"
    kill -- -"${SERVER_PID}" 2>/dev/null || kill "${SERVER_PID}" 2>/dev/null || true
  fi

  _phase_screenshot_archive_finalize

  printf '\n\033[1;32m  Flow 1 GUI E2E finished.\033[0m\n'
  printf '\033[1;32m  Session log: %s\033[0m\n\n' "${SESSION_DIR}"
}

main "$@"
