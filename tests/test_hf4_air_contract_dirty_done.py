"""HF-4: air_contract_sanitize must not dirty-done or freeze when heal refuses.

Do not start a run. HF-5 Pass-2 gap dirt, HR-4 W1 sanitize mute, F2 bind stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_sanitize.air_script import run_air_contract_sanitize
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.run_context import RunContext
from interview_mux.seat_authority import read_seat_freeze, soft_freeze_active
from interview_mux.stage_completion import (
    incompleteness_resume_stage,
    parse_resume_stage_from_reason,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx, mark_done_raw, minimal_gap_line, minimal_gap_report

_REASON = "air_contract_unsanitary — resume air_contract_sanitize: seats_over_wavs"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hf4_air_contract")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_contract(ctx: RunContext) -> None:
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_a",
            text="Line A",
            targets_segment_id="seg_001",
            delivery="synthesize",
        )
    )
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "plan_status": "complete",
            "air_script": {
                "beats": [{"beat_id": "b1"}],
                "vo_seats": {"seated_line_ids": ["vo_a"], "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/omit_ledger.json",
        {"version": 1, "entries": [], "summary": {"active_count": 0}},
        skip_handoff=True,
    )


def test_hf4_heal_refuse_does_not_mark_or_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.clamp_hosted_seats_to_rendered_wavs",
        lambda _ctx: [],
    )
    _plant_contract(ctx)

    def _refuse(_ctx, stage, *, force=False):
        return {
            "stage": stage,
            "marked": False,
            "unmarked": False,
            "refused": True,
            "reason": _REASON,
        }

    monkeypatch.setattr(
        "interview_mux.stage_completion.heal_or_refuse_mark",
        _refuse,
    )
    with pytest.raises(RuntimeError, match="air_contract_sanitize"):
        run_air_contract_sanitize(ctx)
    assert not ctx.is_done("air_contract_sanitize")
    assert not soft_freeze_active(ctx)
    assert not read_seat_freeze(ctx).get("soft")


def test_hf4_sanitary_run_marks_and_freezes(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.clamp_hosted_seats_to_rendered_wavs",
        lambda _ctx: [],
    )
    _plant_contract(ctx)
    run_air_contract_sanitize(ctx)
    assert ctx.is_done("air_contract_sanitize")
    assert soft_freeze_active(ctx)


def test_hf4_incompleteness_pins_air_contract_sanitize(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_contract(ctx)
    mark_done_raw(ctx, "air_contract_sanitize")
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.air_contract_sanitary_errors",
        lambda _ctx: ["seats_over_wavs"],
    )
    reason = stage_artifact_incompleteness(ctx, "air_contract_sanitize")
    assert reason is not None
    assert "air_contract_unsanitary" in reason
    assert "resume air_contract_sanitize" in reason
    assert parse_resume_stage_from_reason(reason) == "air_contract_sanitize"
    assert producer_pin_for_token(reason, ctx=ctx) == "air_contract_sanitize"
    assert incompleteness_resume_stage(ctx, "air_contract_sanitize") == "air_contract_sanitize"
    assert seed_stage_complete(ctx, "air_contract_sanitize") is False
    nav = heal_navigate(ctx, error=reason, stage="air_contract_sanitize")
    assert nav["from_stage"] == "air_contract_sanitize"
    assert nav["from_stage"] != "edl"
