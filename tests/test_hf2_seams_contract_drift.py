"""HF-2: air_script_seams must not fail-open a drifting Pass B commit."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.air_script import SEAMS_CONTRACT_DRIFT_REL, run_air_script_seams, write_plan
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.mastering_plan_loader import load_plan_raw
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_PRIOR_SEATS = ["vo_keep"]


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: True)
    monkeypatch.setattr(
        "interview_mux.air_script.air_script_cfg",
        lambda: {"enable": True, "fail_open": True},
    )
    return isolated_run_ctx(tmp_path, "hf2_seams_drift")


def _plant_prior(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_keep",
                    "delivery": "synthesize",
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "Omitted keep.",
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "plan_status": "complete",
            "air_script": {
                "beats": [{"beat_id": "b1"}],
                "vo_seats": {"seated_line_ids": list(_PRIOR_SEATS), "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )


def _dirty_pass_b(ctx: RunContext) -> dict:
    plan = dict(load_plan_raw(ctx) or {})
    plan["_pass_b_dirty"] = True
    script = dict(plan.get("air_script") or {})
    seats = dict(script.get("vo_seats") or {})
    seats["seated_line_ids"] = ["ghost_vo"]
    script["vo_seats"] = seats
    plan["air_script"] = script
    write_plan(ctx, plan)
    return plan


def test_hf2_drift_rolls_back_plan_and_raises(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_prior(ctx)
    monkeypatch.setattr("interview_mux.air_script.compose_pass_b", _dirty_pass_b)
    monkeypatch.setattr("interview_mux.air_script.persist_air_script_omits_on_gap_report", lambda _c: None)
    monkeypatch.setattr("interview_mux.air_script.attach_sonic_scenes", lambda _c: None)
    monkeypatch.setattr(
        "interview_mux.vo_contract.sync_vo_contract_after_layup",
        lambda _c: ["seated line ghost_vo missing from gap_report"],
    )
    with pytest.raises(RuntimeError, match="VO contract drift after air_script_seams"):
        run_air_script_seams(ctx)
    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan.get("_pass_b_dirty") is not True
    seats = (plan.get("air_script") or {}).get("vo_seats") or {}
    assert "ghost_vo" not in (seats.get("seated_line_ids") or [])
    assert "vo_keep" in (seats.get("seated_line_ids") or [])
    assert not ctx.is_done("air_script_seams")
    drift = ctx.read_json(SEAMS_CONTRACT_DRIFT_REL)
    assert drift.get("active") is True


def test_hf2_incompleteness_and_seed_refuse_after_raw_done(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_prior(ctx)
    monkeypatch.setattr("interview_mux.air_script.compose_pass_b", _dirty_pass_b)
    monkeypatch.setattr("interview_mux.air_script.persist_air_script_omits_on_gap_report", lambda _c: None)
    monkeypatch.setattr("interview_mux.air_script.attach_sonic_scenes", lambda _c: None)
    monkeypatch.setattr(
        "interview_mux.vo_contract.sync_vo_contract_after_layup",
        lambda _c: ["seated line ghost_vo missing from gap_report"],
    )
    with pytest.raises(RuntimeError, match="VO contract drift"):
        run_air_script_seams(ctx)
    mark_done_raw(ctx, "air_script_seams")
    reason = stage_artifact_incompleteness(ctx, "air_script_seams")
    assert reason is not None
    assert "VO contract drift" in reason
    assert seed_stage_complete(ctx, "air_script_seams") is False
    out = heal_or_refuse_mark(ctx, "air_script_seams", force=True)
    assert out.get("marked") is not True
    assert not ctx.is_done("air_script_seams") or out.get("unmarked")


def test_hf2_compose_crash_fail_closed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_prior(ctx)

    def _boom(_ctx):
        raise RuntimeError("compose_boom")

    monkeypatch.setattr("interview_mux.air_script.compose_pass_b", _boom)
    with pytest.raises(RuntimeError, match="compose_boom"):
        run_air_script_seams(ctx)
    assert not ctx.is_done("air_script_seams")
    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan.get("_pass_b_dirty") is not True
    drift = ctx.read_json(SEAMS_CONTRACT_DRIFT_REL)
    assert drift.get("active") is True
