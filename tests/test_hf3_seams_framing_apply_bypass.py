"""HF-3: air_script_seams must not skip an incomplete selection_framing_apply.

Stale mastering_plan after Pass-2 is not a seams allow. Freeze+EDL seal stays.
Do not start a run. HF-2 drift fail-closed stays. Do not reopen HF-1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus.runtime import _seed_prereq_block
from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER
from run_fixtures import isolated_run_ctx, mark_done_raw

_APPLY = "selection_framing_apply"
_SEAMS = "air_script_seams"
_STALE_REASONS = (
    "invalidated_by:gap_framing_recompose",
    "invalidated_by:nugget_layup_compose",
    "invalidated_by:refinement_agenda",
)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, stage: _ctx.is_done(stage),
    )
    return isolated_run_ctx(tmp_path, "hf3_seams_apply")


def _mark_delivery_before_apply(ctx: RunContext) -> None:
    for sid in DELIVERY_ORDER:
        if sid == _APPLY:
            break
        mark_done_raw(ctx, sid)


def _write_stale_plan(ctx: RunContext, reason: str) -> None:
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {"beats": [], "vo_seats": {"seated_line_ids": [], "omitted_line_ids": []}},
            "_meta": {"stale": True, "stale_reason": reason},
        },
        skip_handoff=True,
    )


def test_hf3_stale_plan_still_blocks_seams_on_apply(ctx: RunContext) -> None:
    _mark_delivery_before_apply(ctx)
    _write_stale_plan(ctx, _STALE_REASONS[0])
    assert _seed_prereq_block(ctx, _SEAMS) == _APPLY
    assert not ctx.is_done(_APPLY)


@pytest.mark.parametrize("reason", _STALE_REASONS)
def test_hf3_all_pass2_stale_reasons_block_seams(ctx: RunContext, reason: str) -> None:
    _mark_delivery_before_apply(ctx)
    _write_stale_plan(ctx, reason)
    assert _seed_prereq_block(ctx, _SEAMS) == _APPLY


def test_hf3_does_not_unlink_apply_marker(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_delivery_before_apply(ctx)
    mark_done_raw(ctx, _APPLY)
    _write_stale_plan(ctx, _STALE_REASONS[0])

    def _seed_ok(_ctx: RunContext, stage: str) -> bool:
        if stage == _APPLY:
            return False
        return _ctx.is_done(stage)

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        _seed_ok,
    )
    assert _seed_prereq_block(ctx, _SEAMS) == _APPLY
    assert ctx.is_done(_APPLY)


def test_hf3_freeze_plus_edl_still_allows_seams(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import seat_authority as sa

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        lambda _ctx: ["vo_layup_seg_001"],
    )
    monkeypatch.setattr(
        "interview_mux.air_script.omitted_vo_line_ids",
        lambda _ctx: [],
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "delivery": "synthesize",
                    "text": "Hello.",
                    "required": True,
                }
            ]
        },
        skip_handoff=True,
    )
    from run_fixtures import plant_primary_and_stamp

    _mark_delivery_before_apply(ctx)
    plant_primary_and_stamp(ctx, _APPLY)
    mark_done_raw(ctx, "edl")
    sa.stamp_hard_seat_freeze(ctx, reason="vo_synthesize")
    _write_stale_plan(ctx, _STALE_REASONS[0])
    assert _seed_prereq_block(ctx, _SEAMS) is None
    assert ctx.is_done(_APPLY)
