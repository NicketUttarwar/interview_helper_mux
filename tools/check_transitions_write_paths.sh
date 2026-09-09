#!/usr/bin/env bash
# Fail CI when master/transitions.json is written outside the allowlisted set.
# Prefer persist_transitions_doc (sanitize + retain) over raw write_json.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ALLOWLIST=(
  "src/interview_mux/transition_vo.py"
  "src/interview_mux/artifact_sanitize/transitions.py"
  "src/interview_mux/artifact_sanitize/one_writer.py"
  "src/interview_mux/air_order_integrity.py"
  "src/interview_mux/stages/selection.py"
  "src/interview_mux/tools/sanitize_run.py"
  "src/interview_mux/seam_glue.py"
  # Callers that route through persist_transitions_doc / write_json (admitted):
  "src/interview_mux/artifact_repairs.py"
  "src/interview_mux/edl_narrative_remutate.py"
  "src/interview_mux/edl_overlap_repair.py"
  "src/interview_mux/recovery_controller.py"
  "src/interview_mux/timeline_optimizer/apply.py"
)

PATTERN='write_json\("master/transitions\.json"|write_json\([^)]*transitions\.json|write_committed_json\([^)]*transitions\.json|write_validated_artifact\([^)]*transitions\.json|persist_transitions_doc\(|make_stage_persist\("master/transitions\.json"'

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
    echo "transitions write outside allowlist: $hit"
    violations=$((violations + 1))
  fi
done < <(rg -n "$PATTERN" src --glob '*.py' || true)

if [[ $violations -gt 0 ]]; then
  echo "Found $violations raw master/transitions.json write(s). Route through persist_transitions_doc or add to ALLOWLIST with justification."
  exit 1
fi
echo "check_transitions_write_paths: ok"
