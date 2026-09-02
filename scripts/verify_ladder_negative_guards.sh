#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY=python3
fi
"$PY" -m pytest tests/test_ladder_negative_guards.py tests/test_bounded_invalidation_profiles.py -q
"$PY" -m pytest tests/test_edl_vo_coverage_ladder.py tests/test_execution_contract_ladder.py tests/test_remediation_framework.py -q
