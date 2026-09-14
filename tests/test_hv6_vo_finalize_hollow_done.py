"""HV-6: sound_design_vo_finalize must not hollow-complete.

Missing SDP / invalid SDP refuse done. Skip stub only for no cues.
Do not start a run. C-02 WAV refuse stays.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.analysis_memory import default_sound_design_plan
from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    stage_artifact_incompleteness,
)
from interview_mux.stages.sound_design_vo_finalize import (
    FINALIZE_REL,
    run_sound_design_vo_finalize,
)
from run_fixtures import isolated_run_ctx, mark_done_raw, write_fixture_vo_wav


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "hv6_finalize")


def test_hv6_missing_sdp_refuses_done(ctx: RunContext) -> None:
    run_sound_design_vo_finalize(ctx)
    assert not ctx.is_done("sound_design_vo_finalize")
    doc = ctx.read_json(FINALIZE_REL)
    assert doc.get("refused") is True
    assert doc.get("reason") == "no_sound_design_plan"
    reason = stage_artifact_incompleteness(ctx, "sound_design_vo_finalize")
    assert reason is not None
    assert "sound_design_plan" in reason
    assert seed_stage_complete(ctx, "sound_design_vo_finalize") is False


def test_hv6_validation_fail_refuses_done(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    pickup = ctx.path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)
    write_fixture_vo_wav(pickup / "line_001.wav", duration_sec=0.4)
    plan = default_sound_design_plan()
    plan["assets"] = [
        {
            "asset_id": "vo_bridge_1",
            "role": "vo_bridge",
            "description": "VO",
            "duration_seconds": 1.0,
        }
    ]
    plan["flow_plans"]["podcast"]["cues"] = [
        {
            "cue_id": "cue_1",
            "asset_id": "vo_bridge_1",
            "line_id": "line_001",
            "placement": "before_segment",
        }
    ]
    ctx.write_json("understanding/sound_design_plan.json", plan, skip_handoff=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "delivery": "record",
                    "text": "Hello.",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.stages.sound_design_vo_finalize.validate_sound_design_plan",
        lambda _plan: ["(root): missing required field"],
    )
    run_sound_design_vo_finalize(ctx)
    assert not ctx.is_done("sound_design_vo_finalize")
    doc = ctx.read_json(FINALIZE_REL)
    assert doc.get("errors")
    reason = stage_artifact_incompleteness(ctx, "sound_design_vo_finalize")
    assert reason is not None
    assert "SDP invalid" in reason
    assert seed_stage_complete(ctx, "sound_design_vo_finalize") is False


def test_hv6_no_cues_skip_stub_completes(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/sound_design_plan.json",
        default_sound_design_plan(),
        skip_handoff=True,
    )
    run_sound_design_vo_finalize(ctx)
    doc = ctx.read_json(FINALIZE_REL)
    assert doc.get("skipped") is True
    assert doc.get("reason") == "no_vo_bridge_cues"
    assert doc.get("refused") is not True
    assert ctx.is_done("sound_design_vo_finalize")
    assert seed_stage_complete(ctx, "sound_design_vo_finalize") is True


def test_hv6_raw_done_without_sidecar_incomplete(ctx: RunContext) -> None:
    mark_done_raw(ctx, "sound_design_vo_finalize")
    reason = stage_artifact_incompleteness(ctx, "sound_design_vo_finalize")
    assert reason is not None
    assert FINALIZE_REL in reason or "pending" in reason
    assert seed_stage_complete(ctx, "sound_design_vo_finalize") is False
    out = heal_or_refuse_mark(ctx, "sound_design_vo_finalize")
    assert out.get("unmarked") is True or not ctx.is_done("sound_design_vo_finalize")


def test_hv6_refuse_sidecar_stays_incomplete_after_raw_done(ctx: RunContext) -> None:
    ctx.write_json(
        FINALIZE_REL,
        {"skipped": False, "refused": True, "reason": "no_sound_design_plan"},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "sound_design_vo_finalize")
    assert seed_stage_complete(ctx, "sound_design_vo_finalize") is False
    out = heal_or_refuse_mark(ctx, "sound_design_vo_finalize")
    assert out.get("unmarked") is True or not ctx.is_done("sound_design_vo_finalize")
