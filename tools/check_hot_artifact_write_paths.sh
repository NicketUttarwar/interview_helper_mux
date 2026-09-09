#!/usr/bin/env bash
# Hot-artifact write hygiene:
# - selection boundary allowlist
# - ban tools fs_write_json of selection / edl / gap_report
# - ban tools write_json of selection (must use commit_selection_mutation)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

violations=0

"$ROOT/tools/check_selection_write_paths.sh"

while IFS= read -r hit; do
  [[ -z "$hit" ]] && continue
  echo "banned fs_write_json of hot artifact: $hit"
  violations=$((violations + 1))
done < <(rg -n 'fs_write_json\([^)]*(selection\.json|master/edl\.json|/edl\.json|gap_report\.json)' tools --glob '*.py' || true)

while IFS= read -r hit; do
  [[ -z "$hit" ]] && continue
  echo "tools selection write should use commit_selection_mutation: $hit"
  violations=$((violations + 1))
done < <(rg -n 'write_json\("master/selection\.json"|write_json\([^)]*master/selection\.json' tools --glob '*.py' || true)

if [[ $violations -gt 0 ]]; then
  echo "Found $violations hot-artifact write path violation(s)."
  exit 1
fi

echo "check_hot_artifact_write_paths: ok"
