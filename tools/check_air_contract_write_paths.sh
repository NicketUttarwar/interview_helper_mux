#!/usr/bin/env bash
# Fail CI when mastering_plan / omit_ledger are written outside air-contract allowlist.
# W3: seats + omit + gap VO flags should funnel through commit_air_contract / write_plan.
# Ratcheted: producers mutate in memory then commit; only def-sites + I/O shells remain.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ALLOWLIST=(
  "src/interview_mux/artifact_sanitize/air_script.py"
  "src/interview_mux/mastering_plan_loader.py"
  "src/interview_mux/omit_ledger.py"
  # Legacy composers still call write_plan (which commits air-contract).
  "src/interview_mux/air_script.py"
  "src/interview_mux/chapter_close_hitch.py"
  "src/interview_mux/execution_contract.py"
  "src/interview_mux/listen_quality.py"
  "src/interview_mux/mastering_shape_runtime.py"
  "src/interview_mux/nugget_layup.py"
  "src/interview_mux/vo_contract.py"
)

PATTERN='write_json\("mastering/mastering_plan\.json"|write_json\([^)]*mastering_plan\.json|write_json\("understanding/omit_ledger\.json"|write_json\([^)]*omit_ledger\.json|write_plan\(|write_omit_ledger\(|write_committed_json\([^)]*mastering_plan|write_committed_json\([^)]*omit_ledger|write_validated_artifact\([^)]*mastering_plan|write_validated_artifact\([^)]*omit_ledger'

violations=0
while IFS= read -r hit; do
  file="${hit%%:*}"
  # Def-site of write helpers themselves
  if [[ "$file" == "src/interview_mux/mastering_plan_loader.py" ]] || [[ "$file" == "src/interview_mux/omit_ledger.py" ]]; then
    continue
  fi
  skip=0
  for allowed in "${ALLOWLIST[@]}"; do
    if [[ "$file" == "$allowed" ]]; then
      skip=1
      break
    fi
  done
  if [[ "$file" == tests/* ]]; then
    skip=1
  fi
  if [[ $skip -eq 0 ]]; then
    echo "air_contract write outside allowlist: $hit"
    violations=$((violations + 1))
  fi
done < <(rg -n "$PATTERN" src --glob '*.py' || true)

if [[ $violations -gt 0 ]]; then
  echo "Found $violations raw mastering_plan/omit_ledger write(s). Route through commit_air_contract / write_plan or add to ALLOWLIST with justification."
  exit 1
fi
echo "check_air_contract_write_paths: ok"
