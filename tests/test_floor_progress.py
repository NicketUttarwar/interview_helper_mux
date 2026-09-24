"""Progress-first floor policy — advisory SSOT."""

from __future__ import annotations

from interview_mux.floor_progress import (
    FloorSpec,
    evaluate_floor,
    floor_miss_blocks_progress,
    has_floor_advisories,
    hosted_vo_aspirational,
    is_progress_floors_enabled,
    proceed_on_floor_miss,
    record_floor_advisory,
)
from run_fixtures import isolated_run_ctx


def test_progress_floors_enabled_by_default(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_pf_on")
    assert is_progress_floors_enabled(ctx) is True
    assert hosted_vo_aspirational(ctx) is True


def test_floor_miss_does_not_block_when_enabled(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_pf_block")
    assert floor_miss_blocks_progress(ctx, "hosted_vo_floor") is False
    assert floor_miss_blocks_progress(ctx, "hosted_vo_floor_unsatisfiable") is False
    assert floor_miss_blocks_progress(ctx, "min_layup_coverage") is False
    assert floor_miss_blocks_progress(ctx, "master_exists_nonempty") is True
    assert floor_miss_blocks_progress(ctx, "hosted_vo_wav_coverage") is True


def test_evaluate_floor_stretch_then_miss(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_pf_eval")
    spec = FloorSpec(gate_id="hosted_vo_floor", goal=3, domain="hosted_vo")
    ev = evaluate_floor(ctx, spec, have=2)
    assert ev.status in {"stretch_needed", "miss_advisory"}
    assert ev.have == 2
    assert ev.goal == 3
    met = evaluate_floor(ctx, spec, have=3)
    assert met.status == "met"


def test_proceed_on_floor_miss_records_advisory(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_pf_adv")
    proceed_on_floor_miss(
        ctx,
        gate_id="hosted_vo_floor",
        have=2,
        need=3,
        pool_exhausted=True,
    )
    assert has_floor_advisories(ctx) is True
    meta = ctx.read_json("run_meta.json")
    assert meta.get("floor_aspirational_proceeded") is True
    advisories = meta.get("floor_advisories") or []
    assert advisories
    assert advisories[-1]["gate_id"] == "hosted_vo_floor"
    assert advisories[-1]["detail"]["have"] == 2
    assert advisories[-1]["detail"]["need"] == 3


def test_record_floor_advisory_clears_hosted_thrash_stamps(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_pf_clear")

    def _stamp(meta: dict) -> None:
        meta["hosted_vo_floor_unmet"] = True
        meta["hosted_vo_floor_unsatisfiable"] = True
        meta["needs_operator"] = True
        meta["needs_operator_reason"] = "hosted_vo_floor_unmet"

    ctx.mutate_run_meta(_stamp)
    record_floor_advisory(
        ctx,
        "hosted_vo_floor",
        {"have": 1, "need": 3},
        aspirational_proceeded=True,
        mirror_quality=False,
    )
    meta = ctx.read_json("run_meta.json")
    assert "hosted_vo_floor_unmet" not in meta or meta.get("hosted_vo_floor_unmet") is None
    assert meta.get("needs_operator_reason") != "hosted_vo_floor_unmet"
