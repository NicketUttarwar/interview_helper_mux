#!/usr/bin/env bash
# Aggregator for artifact write-path allowlist scripts (Ship 6).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SCRIPTS=(
  check_selection_write_paths.sh
  check_gap_write_paths.sh
  check_air_contract_write_paths.sh
  check_transitions_write_paths.sh
  check_edl_write_paths.sh
  check_one_writer_fs_bypass.sh
)

failed=0
for s in "${SCRIPTS[@]}"; do
  echo "==> tools/$s"
  if ! bash "$ROOT/tools/$s"; then
    failed=1
  fi
done

if [[ $failed -ne 0 ]]; then
  echo "check_artifact_write_paths: FAILED"
  exit 1
fi
echo "check_artifact_write_paths: ok"
