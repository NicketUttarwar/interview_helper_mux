#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi
cd "$ROOT"
"$PY" tools/bootstrap_stage_contracts.py
"$PY" tools/codegen_openai_schemas.py
"$PY" tools/extract_stage_dependencies.py
"$PY" tools/codegen_from_contracts.py
"$PY" tools/verify_dependency_graph.py
"$PY" tools/verify_stage_contracts.py
"$PY" tools/codegen_artifact_manifest.py
"$PY" tools/progression_chain_sanity.py --scope full
"$PY" -m pytest tests/test_openai_schema_semantic_lint.py \
  tests/test_openai_structured_output.py \
  tests/test_golden_envelope_schema_validate.py \
  tests/test_stage_contracts_drift.py \
  tests/test_artifact_dependency_graph.py \
  tests/test_sufficiency_engine.py \
  tests/test_micro_gap_fill.py \
  tests/test_remediation_orchestrator.py \
  tests/test_artifact_lifecycle.py \
  tests/test_downstream_probe.py \
  tests/test_progression_readiness.py \
  tests/test_runtime_golden_path.py \
  tests/test_artifact_manifest.py -q
