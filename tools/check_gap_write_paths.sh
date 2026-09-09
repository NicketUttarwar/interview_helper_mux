#!/usr/bin/env bash
# Fail CI when understanding/gap_report.json is written outside the allowlisted set.
# W1 sanitize owns non-amplifying cleanup; producers remain allowlisted with justification.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ALLOWLIST=(
  "src/interview_mux/artifact_sanitize/gap_report.py"
  "src/interview_mux/artifact_sanitize/one_writer.py"
  "src/interview_mux/artifact_sanitize/air_script.py"
  "src/interview_mux/air_script.py"
  "src/interview_mux/artifact_cross_validate.py"
  "src/interview_mux/artifact_repairs.py"
  "src/interview_mux/chapter_close_hitch.py"
  "src/interview_mux/edl_narrative_remutate.py"
  "src/interview_mux/execution_contract.py"
  "src/interview_mux/omit_ledger.py"
  "src/interview_mux/opening_orientation.py"
  "src/interview_mux/opening_adjacency_repair.py"
  "src/interview_mux/recovery_controller.py"
  "src/interview_mux/refinement_passes.py"
  "src/interview_mux/s2s_runner.py"
  "src/interview_mux/stages/assembly.py"
  "src/interview_mux/stages/gaps.py"
  "src/interview_mux/synthesis_fallback.py"
  "src/interview_mux/timeline_optimizer/apply.py"
  "src/interview_mux/vo_contract.py"
  "src/interview_mux/vo_line_adjudicate.py"
  "src/interview_mux/web/server.py"
  "src/interview_mux/nugget_layup.py"
)

PATTERN='write_json\("understanding/gap_report\.json"|write_json\([^)]*gap_report\.json|write_committed_json\([^)]*gap_report\.json|write_validated_artifact\([^)]*gap_report\.json|fs_write_json\([^)]*gap_report'

violations=0
while IFS= read -r hit; do
  file="${hit%%:*}"
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
    echo "gap_report write outside allowlist: $hit"
    violations=$((violations + 1))
  fi
done < <(rg -n "$PATTERN" src --glob '*.py' || true)

if [[ $violations -gt 0 ]]; then
  echo "Found $violations raw gap_report.json write(s). Route through sanitize commit or add to ALLOWLIST with justification."
  exit 1
fi
echo "check_gap_write_paths: ok"
