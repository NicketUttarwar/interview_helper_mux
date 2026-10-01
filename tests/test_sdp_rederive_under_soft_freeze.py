"""The sound design plan's producer may re-derive a plan the selection has outgrown (ISSUES 104)."""

from __future__ import annotations

import json

from run_fixtures import isolated_run_ctx

from interview_mux.seat_authority import (
    frozen_seat_write_allowed,
    sound_design_plan_stale_versus_selection,
    stamp_hard_seat_freeze,
    stamp_soft_seat_freeze,
)

SDP = "understanding/sound_design_plan.json"


def _seed(ctx, *, anchor: str, ordered: list[str]) -> None:
    p = ctx.final_path("understanding", "sound_design_plan.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "version": 1,
                "flow_plans": {"podcast": {"cues": [{"cue_id": "bed_coverage_seed_1", "segment_id": anchor}]}},
            }
        ),
        encoding="utf-8",
    )
    s = ctx.final_path("master", "selection.json")
    s.parent.mkdir(parents=True, exist_ok=True)
    s.write_text(json.dumps({"version": 1, "ordered_segment_ids": ordered, "excluded_segment_ids": []}), encoding="utf-8")


def test_stale_plan_may_be_rewritten_by_its_producer_under_soft_freeze(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_sdp_stale_soft")
    _seed(ctx, anchor="seg_007", ordered=["seg_001", "seg_002"])
    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    assert sound_design_plan_stale_versus_selection(ctx) is True
    assert frozen_seat_write_allowed(ctx, SDP, reason="sound_design_plan") is True


def test_a_coherent_plan_may_still_be_landed_by_its_producer_under_soft_freeze(tmp_path) -> None:
    # ISSUES 116 widened entry 104: the producer's own write lands under the
    # soft freeze whether or not the plan on disk is stale; the hard freeze
    # and foreign writers are unchanged (tests below).
    ctx = isolated_run_ctx(tmp_path, "exec_sdp_coherent_soft")
    _seed(ctx, anchor="seg_001", ordered=["seg_001", "seg_002"])
    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    assert sound_design_plan_stale_versus_selection(ctx) is False
    assert frozen_seat_write_allowed(ctx, SDP, reason="sound_design_plan") is True


def test_hard_freeze_still_refuses_even_a_stale_plan(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_sdp_stale_hard")
    _seed(ctx, anchor="seg_007", ordered=["seg_001", "seg_002"])
    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    assert frozen_seat_write_allowed(ctx, SDP, reason="sound_design_plan") is False


def test_other_writers_get_no_carve_out(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_sdp_stale_other")
    _seed(ctx, anchor="seg_007", ordered=["seg_001", "seg_002"])
    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    assert frozen_seat_write_allowed(ctx, SDP, reason="mix") is False
