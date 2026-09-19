#!/usr/bin/env bash
# Residual regress harness — End-A…F + cousins + soft-pass/hollow/ownership + HX
# + optional R* modules when present. Also runs ownership write-site audit and
# full-auto soft-env verify.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

export MUX_FORENSICS=0

PYTEST_TARGETS=(
  tests/test_enda_hard_freeze_constitution.py
  tests/test_endb_flush_bind_authority.py
  tests/test_endc_glue_before_edl.py
  tests/test_endd_commitment_seating.py
  tests/test_ende_heal_stamp_pin.py
  tests/test_endf_pmq_score_honesty.py
  tests/test_end_cousin_fixtures.py
  tests/test_opening_orientation.py
  tests/test_i24_commitment_remaster.py
  tests/test_i25_pmq_omit_clarity.py
  tests/test_soft_pass_pre_edl_refuse.py
  tests/test_hollow_seed_sanitary.py
  tests/test_artifact_ownership_constitution.py
  tests/test_gui_ownership_role.py
  tests/test_hx1_mix_epoch_unsealed.py
  tests/test_hx2_mix_unseated.py
  tests/test_hx4_mix_lease_pin.py
  tests/test_anti_footgun_hardening.py
  tests/test_category_b_footguns.py
  tests/test_category_b_ws1_shape.py
  tests/test_category_b_ws2_highgap.py
  tests/test_category_b_ws4_ownership.py
  tests/test_category_b_ws5_conductor.py
  tests/test_ws3_edl_narrative_disk_gate.py
  tests/test_r1_orientation_heal_pin.py
  tests/test_r2_scaffold_sanitize.py
  tests/test_r3_vo_family.py
  tests/test_r4_premature.py
  tests/test_r5_mix_seat.py
  tests/test_r6_edl_budget.py
  tests/test_r7_pmq_honesty.py
  tests/test_r_workflow_residual.py
  tests/test_r_schema_parity.py
  tests/test_r_gui_attended.py
)

echo "check_residual_regress: pytest (${#PYTEST_TARGETS[@]} targets) MUX_FORENSICS=0"
"$PY" -m pytest -q "${PYTEST_TARGETS[@]}"

echo "check_residual_regress: audit_artifact_ownership --write-sites-only"
"$PY" tools/audit_artifact_ownership.py --write-sites-only

echo "check_residual_regress: ownership_new_stage_checklist"
"$PY" tools/ownership_new_stage_checklist.py

echo "check_residual_regress: verify_full_auto_env"
./tools/verify_full_auto_env.sh

echo "check_residual_regress: OK"
