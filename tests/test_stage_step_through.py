"""Step-through pause before pipeline stages."""

from __future__ import annotations

import pytest

from interview_mux.stage_step_through import (
    StageStepThroughPending,
    confirm_step_through,
    pending_step_through_stage,
    require_step_through_before_stage,
    step_through_enabled,
)
from interview_mux.run_context import RunContext


@pytest.fixture
def step_through_on(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.stage_step_through.merged_config",
        lambda: {
            "journey_ui": {
                "step_through_between_stages": True,
                "step_through_pause_seconds": 10,
            }
        },
    )


def test_step_through_raises_when_not_approved(tmp_path, monkeypatch, step_through_on) -> None:
    monkeypatch.setattr(
        "interview_mux.run_context.repo_root",
        lambda: tmp_path,
    )
    ctx = RunContext("exec_001_20260101T000001Z")
    ctx.init_run_meta("ASSETS/input/interview.wav")
    with pytest.raises(StageStepThroughPending) as exc:
        require_step_through_before_stage(ctx, "ingest")
    assert exc.value.stage_id == "ingest"
    assert pending_step_through_stage(ctx) == "ingest"


def test_step_through_proceed_allows_rerun(tmp_path, monkeypatch, step_through_on) -> None:
    monkeypatch.setattr(
        "interview_mux.run_context.repo_root",
        lambda: tmp_path,
    )
    ctx = RunContext("exec_002_20260101T000002Z")
    ctx.init_run_meta("ASSETS/input/interview.wav")
    with pytest.raises(StageStepThroughPending):
        require_step_through_before_stage(ctx, "ingest")
    confirm_step_through(ctx, "ingest", "proceed")
    require_step_through_before_stage(ctx, "ingest")


def test_step_through_skip_marks_done(tmp_path, monkeypatch, step_through_on) -> None:
    monkeypatch.setattr(
        "interview_mux.run_context.repo_root",
        lambda: tmp_path,
    )
    ctx = RunContext("exec_003_20260101T000003Z")
    ctx.init_run_meta("ASSETS/input/interview.wav")
    with pytest.raises(StageStepThroughPending):
        require_step_through_before_stage(ctx, "ingest")
    confirm_step_through(ctx, "ingest", "skip")
    assert ctx.is_done("ingest")
    require_step_through_before_stage(ctx, "ingest")


def test_step_through_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.run_context.repo_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "interview_mux.stage_step_through.merged_config",
        lambda: {"journey_ui": {"step_through_between_stages": False}},
    )
    ctx = RunContext("exec_004_20260101T000004Z")
    ctx.init_run_meta("ASSETS/input/interview.wav")
    require_step_through_before_stage(ctx, "ingest")
    assert not step_through_enabled()
