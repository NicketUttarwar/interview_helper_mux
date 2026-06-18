#!/usr/bin/env bash
# June 2026 build — run all CURSOR_EXECUTE steps, then git add / commit / push after each.
#
# ONE COMMAND (from repo root):
#   ./docs/build-out/june182026build/run.sh
#
# After every successful agent step this script runs (at repo root):
#   git add .
#   git commit -m "<short message for that step>"
#   git push origin main
#
# Assumes git is authenticated for origin/main. Use --no-git to skip pushes.
# Usage:
#   ./docs/build-out/june182026build/run.sh
#   ./docs/build-out/june182026build/run.sh --dry-run
#   ./docs/build-out/june182026build/run.sh --no-git
#   ./docs/build-out/june182026build/run.sh --from 3 --to 3
#   ./docs/build-out/june182026build/run.sh --resume
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/scripts/lib/secrets_env.sh"
load_secrets_env "${REPO_ROOT}"
COMMANDS_MD="${SCRIPT_DIR}/agent-commands.md"
EXEC_RUN="${REPO_ROOT}/CURSOR_EXECUTE/run.sh"
ONE_LINER="cd ${REPO_ROOT} && ./docs/build-out/june182026build/run.sh"

# step → short commit message (after "june182026build: ")
declare -a STEP_MSG=(
  ""
  "step 01 SETUP preflight"
  "step 02 Wave 0 resilience harness"
  "step 03 Wave A early truth"
  "step 04 Wave B audio structure"
  "step 05 Wave C self-healing"
  "step 06 Wave D output resilience"
  "step 07 FINISH sign-off"
)

_git_commit_push() {
  local step="$1"
  local msg="june182026build: ${STEP_MSG[$step]}"
  cd "$REPO_ROOT"
  printf '\n\033[1;33m── git after step %s ──────────────────────────────────\033[0m\n' "$step"
  printf '  git add .\n'
  printf '  git commit -m "%s"\n' "$msg"
  printf '  git push origin main\n\n'
  if git diff --quiet && git diff --cached --quiet; then
    printf '\033[1;33m  (no changes — skipping commit/push)\033[0m\n\n'
    return 0
  fi
  git add .
  git commit -m "$msg"
  git push origin main
  printf '\033[1;32m  pushed step %s to origin/main\033[0m\n\n' "$step"
}

_print_plan_banner() {
  local from="$1" to="$2" dry="$3" no_git="$4"
  printf '\n\033[1;36m════════════════════════════════════════════════════════\033[0m\n'
  printf '\033[1;36m  June 2026 build — automated run\033[0m\n'
  printf '\033[1;36m  Repo:  %s\033[0m\n' "$REPO_ROOT"
  printf '\033[1;36m  Steps: %s → %s (CURSOR_EXECUTE agent sessions)\033[0m\n' "$from" "$to"
  if [[ "$dry" -eq 1 ]]; then
    printf '\033[1;36m  Mode:  DRY-RUN (no API, no git)\033[0m\n'
  elif [[ "$no_git" -eq 1 ]]; then
    printf '\033[1;36m  Mode:  agents only (--no-git)\033[0m\n'
  else
    printf '\033[1;36m  After EACH successful step:\033[0m\n'
    printf '\033[1;36m    git add .\033[0m\n'
    printf '\033[1;36m    git commit -m "june182026build: step NN …"\033[0m\n'
    printf '\033[1;36m    git push origin main\033[0m\n'
    printf '\033[1;36m  (assumes git auth is already configured)\033[0m\n'
  fi
  printf '\033[1;36m════════════════════════════════════════════════════════\033[0m\n\n'
}

_resume_from_index() {
  local state_dir="${REPO_ROOT}/CURSOR_EXECUTE/state"
  local key
  key="$(python3 -c "
import hashlib, pathlib
root = pathlib.Path('${REPO_ROOT}').resolve()
md = pathlib.Path('${COMMANDS_MD}').resolve()
print(hashlib.md5(f'{root}|{md}'.encode()).hexdigest())
")"
  local state_file="${state_dir}/${key}.json"
  if [[ ! -f "$state_file" ]]; then
    echo 1
    return
  fi
  python3 -c "
import json, sys
data = json.loads(open('${state_file}').read())
last = int(data.get('last_completed_index', 0))
print(last + 1 if last > 0 else 1)
"
}

DRY_RUN=0
NO_GIT=0
RESUME=0
FROM_SET=0
TO_SET=0
FROM_STEP=""
TO_STEP=""
EXTRA_ARGS=()
i=1
while [[ $i -le $# ]]; do
  arg="${!i}"
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-git) NO_GIT=1 ;;
    --resume) RESUME=1 ;;
    --from)
      FROM_SET=1
      i=$((i + 1))
      FROM_STEP="${!i}"
      ;;
    --to)
      TO_SET=1
      i=$((i + 1))
      TO_STEP="${!i}"
      ;;
    *)
      EXTRA_ARGS+=("$arg")
      ;;
  esac
  i=$((i + 1))
done

FROM_STEP="${FROM_STEP:-1}"
TO_STEP="${TO_STEP:-7}"

if [[ "$RESUME" -eq 1 && "$FROM_SET" -eq 0 ]]; then
  FROM_STEP="$(_resume_from_index)"
  printf 'Resuming from step %s (CURSOR_EXECUTE state)\n' "$FROM_STEP"
fi

_print_plan_banner "$FROM_STEP" "$TO_STEP" "$DRY_RUN" "$NO_GIT"

FAILED=0
for step in $(seq "$FROM_STEP" "$TO_STEP"); do
  printf '\033[1;35m▶ CURSOR_EXECUTE step %s / %s\033[0m\n' "$step" "$TO_STEP"
  STEP_ARGS=(--from "$step" --to "$step")
  [[ "$DRY_RUN" -eq 1 ]] && STEP_ARGS+=(--dry-run)
  if ! "${EXEC_RUN}" "$COMMANDS_MD" "${STEP_ARGS[@]}" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}; then
    FAILED=1
    break
  fi
  if [[ "$DRY_RUN" -eq 0 && "$NO_GIT" -eq 0 ]]; then
    _git_commit_push "$step"
  fi
done

printf '\n\033[1;36m════════════════════════════════════════════════════════\033[0m\n'
if [[ "$FAILED" -eq 1 ]]; then
  printf '\033[1;31m  Run stopped early — fix the failure, then resume:\033[0m\n'
  printf '\033[1;32m  %s --resume\033[0m\n' "$ONE_LINER"
  printf '\033[1;36m════════════════════════════════════════════════════════\033[0m\n\n'
  exit 1
fi

printf '\033[1;32m  All steps %s–%s finished.\033[0m\n' "$FROM_STEP" "$TO_STEP"
printf '\033[1;32m  Copy-paste to run the full pipeline again:\033[0m\n\n'
printf '  %s\n\n' "$ONE_LINER"
printf '\033[1;36m════════════════════════════════════════════════════════\033[0m\n\n'
