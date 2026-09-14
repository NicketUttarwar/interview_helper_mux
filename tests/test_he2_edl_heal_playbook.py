"""HE-2: rebuild-EDL playbook is not recovered while VO/bind is unsanitary.

Do not start a run. HE-1 audit, HE-3 preview, F2 bind mark, F4 missing-WAV classify stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error, resume_stage_for_error_class
from interview_mux.publishability_boundary import PublishabilityBlocked, PublishabilityReport
from interview_mux.recovery_controller import handle_stage_failure, playbook_rebuild_edl
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import edl_heal_resume_stage, producer_pin_for_token
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx

_LINE = "vo_edl_1"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "he2_edl")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_edl(ctx: RunContext) -> None:
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 0,
            "clips": [],
        },
        skip_handoff=True,
    )


def _plant_unsanitary_seated(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": "Need a heard WAV.",
                    "delivery": "synthesize",
                    "required": True,
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
                "vo_seats": {"seated_line_ids": [_LINE], "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )


def _drift_exc() -> PublishabilityBlocked:
    report = PublishabilityReport(checkpoint="post_edl", ok=False, violations=[])
    return PublishabilityBlocked(report, error_class="vo_audibility_drift")


def test_he2_unsanitary_playbook_does_not_claim_edl(ctx: RunContext) -> None:
    _plant_edl(ctx)
    _plant_unsanitary_seated(ctx)
    assert edl_heal_resume_stage(ctx) == "vo_synthesize"
    assert producer_pin_for_token("vo_audibility_drift", ctx=ctx) == "vo_synthesize"
    route = classify_heal_error("vo_audibility_drift", ctx, stage="edl")
    assert route is not None
    assert route.from_stage == "vo_synthesize"
    assert route.from_stage != "edl"
    nav = heal_navigate(ctx, error="vo_audibility_drift", stage="edl")
    assert nav["from_stage"] == "vo_synthesize"
    assert playbook_rebuild_edl(ctx) == []


def test_he2_sanitary_playbook_may_resume_edl(ctx: RunContext) -> None:
    _plant_edl(ctx)
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []}, skip_handoff=True)
    assert edl_heal_resume_stage(ctx) == "edl"
    assert playbook_rebuild_edl(ctx) == ["master/edl.json"]
    assert resume_stage_for_error_class("vo_audibility_drift") == "edl"
    route = classify_heal_error("opening_orientation_inaudible", ctx, stage="edl")
    assert route is not None
    assert route.from_stage == "edl"


def test_he2_recovery_not_recovered_when_unsanitary(ctx: RunContext) -> None:
    _plant_edl(ctx)
    _plant_unsanitary_seated(ctx)
    result = handle_stage_failure(ctx, "edl", _drift_exc())
    assert result.resume_stage == "vo_synthesize"
    assert result.status != "recovered"
    assert result.playbook_id == "vo_audibility_drift"


def test_he2_recovery_recovered_when_sanitary(ctx: RunContext) -> None:
    _plant_edl(ctx)
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []}, skip_handoff=True)
    result = handle_stage_failure(ctx, "edl", _drift_exc())
    assert result.resume_stage == "edl"
    assert result.status == "recovered"
    assert "master/edl.json" in result.artifacts_written
