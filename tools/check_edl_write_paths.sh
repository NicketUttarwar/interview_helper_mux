#!/usr/bin/env bash
# Fail CI when master/edl.json / assembly_ledger writes bypass the pair bus.
# Prefer write_live_edl (EDL+ledger pair) over ledger-only or bare edl write_json.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ALLOWLIST=(
  "src/interview_mux/air_order.py"
  "src/interview_mux/artifact_sanitize/edl.py"
  "src/interview_mux/artifact_sanitize/one_writer.py"
  "src/interview_mux/assembly_ledger.py"
  "src/interview_mux/stages/assembly.py"
  "src/interview_mux/junction_snip_qa.py"
  "src/interview_mux/segment_id_remap.py"
  "src/interview_mux/edl_source_contract.py"
  "src/interview_mux/edl_overlap_repair.py"
  "src/interview_mux/omit_ledger.py"
  "src/interview_mux/vo_synthesis_audit.py"
  "src/interview_mux/opening_orientation.py"
  "src/interview_mux/sound_design.py"
  "src/interview_mux/transition_vo.py"
  "src/interview_mux/publishability_boundary.py"
  "src/interview_mux/write_staging.py"
  # Seam autopsy may restamp ledger with explicit note — keep allowlisted.
  "src/interview_mux/seam_autopsy.py"
  "src/interview_mux/thrash_hardening.py"
  "src/interview_mux/stage_input_checks.py"
)

PATTERN='write_json\("master/edl\.json"|write_json\([^)]*master/edl\.json|write_live_edl\(|write_json\("master/assembly_ledger\.json"|write_json\([^)]*assembly_ledger\.json|write_assembly_ledger\(|write_committed_json\([^)]*edl\.json|write_validated_artifact\([^)]*edl\.json'

violations=0
while IFS= read -r hit; do
  file="${hit%%:*}"
  # Def-site of write helpers
  if [[ "$file" == "src/interview_mux/air_order.py" ]] || [[ "$file" == "src/interview_mux/assembly_ledger.py" ]]; then
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
    echo "edl/ledger write outside allowlist: $hit"
    violations=$((violations + 1))
  fi
done < <(rg -n "$PATTERN" src --glob '*.py' || true)

if [[ $violations -gt 0 ]]; then
  echo "Found $violations raw EDL/ledger write(s). Route through write_live_edl / write_assembly_ledger or add to ALLOWLIST with justification."
  exit 1
fi
echo "check_edl_write_paths: ok"
