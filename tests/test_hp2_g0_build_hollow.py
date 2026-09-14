"""HP-2: transcript_review_build cannot hollow-done without a schema-valid queue.

Missing file and {} stay incomplete. Empty chunks: [] is allowed. After G0,
rewind must not force-stamp without a queue. Do not start a run. HP-1 sign-off
and HP-4 heal pin stay closed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import (
    _refuse_delivery_timeline_rewind,
    skip_stage,
    stage_outputs_present,
    unmark_hollow_prepare_stages,
)
from interview_mux.homunculus.runtime import dispatch_stage
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    g0_heal_resume_stage,
    heal_or_refuse_mark,
    parse_resume_stage_from_reason,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_STAGE = "transcript_review_build"
_QUEUE = "transcript/review_queue.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hp2_g0_build")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_hollow_queue(ctx: RunContext) -> None:
    dest = ctx.final_path("transcript", "review_queue.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("{}", encoding="utf-8")


def _close_g0(ctx: RunContext) -> None:
    ctx.write_json(
        "transcript/full.json",
        {"text": "Hello from the reviewed tape."},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "transcript_review")


def test_hp2_missing_queue_is_incomplete(ctx: RunContext) -> None:
    mark_done_raw(ctx, _STAGE)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "pending" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert stage_outputs_present(ctx, _STAGE) is False
    assert seed_stage_complete(ctx, _STAGE) is False
    cleared = unmark_hollow_prepare_stages(ctx)
    assert _STAGE in cleared
    assert not ctx.is_done(_STAGE)
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)
    assert g0_heal_resume_stage(ctx) == _STAGE


def test_hp2_skip_without_queue_refused(ctx: RunContext) -> None:
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, _STAGE, reason="conductor whim")
    assert not ctx.is_done(_STAGE)


def test_hp2_empty_object_is_incomplete(ctx: RunContext) -> None:
    _plant_hollow_queue(ctx)
    mark_done_raw(ctx, _STAGE)
    reason = stage_artifact_incompleteness(ctx, _STAGE)
    assert reason is not None
    assert "schema-hollow" in reason
    assert parse_resume_stage_from_reason(reason) == _STAGE
    assert seed_stage_complete(ctx, _STAGE) is False
    assert g0_heal_resume_stage(ctx) == _STAGE
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("unmarked") is True or not ctx.is_done(_STAGE)


def test_hp2_empty_chunks_is_complete(ctx: RunContext) -> None:
    ctx.write_json(_QUEUE, {"chunks": []}, skip_handoff=True)
    assert stage_artifact_incompleteness(ctx, _STAGE) is None
    assert stage_outputs_present(ctx, _STAGE) is True
    out = heal_or_refuse_mark(ctx, _STAGE)
    assert out.get("marked") is True
    assert ctx.is_done(_STAGE)
    assert seed_stage_complete(ctx, _STAGE) is True
    assert g0_heal_resume_stage(ctx) == "transcript_review"
    doc = skip_stage(ctx, _STAGE, reason="already queued")
    assert _STAGE in doc["skipped"]
    assert ctx.is_done(_STAGE)


def test_hp2_g0_rewind_does_not_force_mark_without_queue(ctx: RunContext) -> None:
    from test_homunculus import _mark_analysis_prefix

    _close_g0(ctx)
    _refuse_delivery_timeline_rewind(ctx, _STAGE, action="run")
    assert not ctx.is_done(_STAGE)
    _mark_analysis_prefix(ctx, _STAGE)
    ran: list[str] = []

    def _impl(sid: str) -> None:
        ran.append(sid)
        ctx.write_json(_QUEUE, {"chunks": []}, skip_handoff=True)

    dispatch_stage(ctx, _STAGE, _impl, source="conductor")
    assert ran == [_STAGE]
    assert ctx.artifact_exists(_QUEUE)


def test_hp2_g0_rewind_refuses_when_queue_complete(ctx: RunContext) -> None:
    _close_g0(ctx)
    ctx.write_json(_QUEUE, {"chunks": []}, skip_handoff=True)
    with pytest.raises(RuntimeError, match="G0 is closed"):
        _refuse_delivery_timeline_rewind(ctx, _STAGE, action="run")
    ran: list[str] = []
    with pytest.raises(RuntimeError, match="G0 is closed"):
        dispatch_stage(ctx, _STAGE, lambda sid: ran.append(sid), source="conductor")
    assert ran == []
    assert ctx.is_done(_STAGE)
