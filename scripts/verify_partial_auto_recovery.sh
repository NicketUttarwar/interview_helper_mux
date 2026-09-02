#!/usr/bin/env bash
# Partial-auto recovery regression subset (Phases 1–6).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Run ./scripts/bootstrap_venv.sh first"
  exit 1
fi
"$PY" -m pytest tests/test_execution_contract_ladder.py tests/test_remediation_framework.py tests/test_execution_flow_hardening.py tests/test_edl_vo_coverage_ladder.py tests/test_bounded_invalidation_profiles.py tests/test_ladder_negative_guards.py -q --tb=short
"$ROOT/scripts/verify_ladder_negative_guards.sh"
