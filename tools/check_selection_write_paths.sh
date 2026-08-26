#!/usr/bin/env bash
# Fail CI when master/selection.json is written outside the boundary bus.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ALLOWLIST=(
  "src/interview_mux/air_order_boundary.py"
  "src/interview_mux/air_order_integrity.py"
  "src/interview_mux/stages/assembly.py"
  "src/interview_mux/synthetic_framing.py"
  "src/interview_mux/refinement_passes.py"
  "src/interview_mux/air_script.py"
  "src/interview_mux/listen_delight_remutate.py"
  "src/interview_mux/artifact_repairs.py"
  "src/interview_mux/media_ip_cta.py"
  "src/interview_mux/order_reconcile.py"
)

PATTERN='write_json\("master/selection\.json"|write_json\(.*master/selection\.json|write_committed_json\([^)]*master/selection\.json|write_validated_artifact\([^)]*master/selection\.json'

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
    echo "selection write outside boundary allowlist: $hit"
    violations=$((violations + 1))
  fi
done < <(rg -n "$PATTERN" src --glob '*.py' || true)

if [[ $violations -gt 0 ]]; then
  echo "Found $violations raw master/selection.json write(s). Route through commit_selection_mutation or add to ALLOWLIST with justification."
  exit 1
fi
echo "check_selection_write_paths: ok"
