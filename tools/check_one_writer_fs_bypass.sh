#!/usr/bin/env bash
# Ban fs_write_json of hot one-writer artifacts outside sanitize / staging / tests.
# write_json / write_committed_json are routed via artifact_sanitize.one_writer.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ALLOWLIST=(
  "src/interview_mux/artifact_sanitize/gap_report.py"
  "src/interview_mux/artifact_sanitize/one_writer.py"
  "src/interview_mux/write_staging.py"
  "src/interview_mux/publishability_boundary.py"
  "src/interview_mux/edl_source_contract.py"
  "src/interview_mux/file_store.py"
)

# Matches fs_write_json(...selection|gap_report|edl|transitions|sound_design|nugget_layup...)
PATTERN='fs_write_json\([^)]*(selection\.json|gap_report\.json|edl\.json|transitions\.json|sound_design_plan\.json|nugget_layup_plan\.json)|fs_write_json\(ctx\.(path|final_path)\([^\)]*(selection|gap_report|edl|transitions|sound_design|nugget_layup|PLAN_REL)'

violations=0
while IFS= read -r hit; do
  [[ -z "$hit" ]] && continue
  file="${hit%%:*}"
  skip=0
  for allowed in "${ALLOWLIST[@]}"; do
    if [[ "$file" == "$allowed" ]]; then
      skip=1
      break
    fi
  done
  if [[ "$file" == src/interview_mux/artifact_sanitize/* ]]; then
    skip=1
  fi
  if [[ "$file" == tests/* ]]; then
    skip=1
  fi
  if [[ $skip -eq 0 ]]; then
    echo "hot fs_write_json outside one-writer allowlist: $hit"
    violations=$((violations + 1))
  fi
done < <(rg -n "$PATTERN" src --glob '*.py' || true)

if [[ $violations -gt 0 ]]; then
  echo "Found $violations hot fs_write_json bypass(es). Route through commit_* / write_live_* / write_json (admitted)."
  exit 1
fi
echo "check_one_writer_fs_bypass: ok"
