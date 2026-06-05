"""Zero-shot flow: verify checkpoints only after artifacts are populated."""

from __future__ import annotations

import pytest

from interview_mux.analysis_memory import ensure_analysis_workspace
from interview_mux.artifact_completeness import (
    analysis_profile_ready_for_review,
    artifact_ready_for_review,
)
from interview_mux.custom_run_handoff import pending_handoff_stage
from interview_mux.gates import (
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    is_operator_profile_verified,
    set_selected_flow,
)
from interview_mux.run_context import RunContext
from interview_mux.web.server import _build_stage_list
from run_fixtures import init_run_meta_for_test, patch_executions_root

COMPLETE_SPEAKERS = {
    "speakers": [
        {
            "speaker_id": "spk_0",
            "role": "interviewer",
            "confidence": 0.95,
            "evidence": ["Opening question pattern"],
        },
        {
            "speaker_id": "spk_1",
            "role": "interviewee",
            "confidence": 0.92,
            "evidence": ["Extended answers"],
        },
    ]
}


def _stage_status(ctx: RunContext, stage_id: str) -> str:
    stages = _build_stage_list(
        ctx,
        None,
        check_g1_vo(ctx),
        check_transcript_review_pending(ctx),
        is_operator_profile_verified(ctx),
        check_profile_gate_pending(ctx),
    )
    return next(s["status"] for s in stages if s["id"] == stage_id)


def test_fresh_run_analysis_profile_locked(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    init_run_meta_for_test(ctx)
    ensure_analysis_workspace(ctx)

    assert _stage_status(ctx, "analysis_profile") == "locked"
    assert not analysis_profile_ready_for_review(ctx)
    meta = ctx.read_json("run_meta.json")
    assert not meta.get("handoff_pending_writes")


def test_analysis_profile_action_required_after_analysis(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    init_run_meta_for_test(ctx)
    ensure_analysis_workspace(ctx)
    ctx.mark_done("optimal_questions")
    state = ctx.read_json("understanding/analysis_state.json")
    state["themes"] = [{"id": "t1", "label": "Theme", "summary": "Summary text"}]
    state["narrative"] = {"thesis": "Core thesis from the interview."}
    state["interview_identity"] = {"one_line_summary": "A conversation about testing."}
    state["completion"] = {"analysis_ready": True, "blockers": []}
    ctx.write_json("understanding/analysis_state.json", state, skip_handoff=True)

    assert analysis_profile_ready_for_review(ctx)
    assert _stage_status(ctx, "analysis_profile") == "action_required"


def test_profile_gate_pending_requires_populated_profile(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    init_run_meta_for_test(ctx)
    ensure_analysis_workspace(ctx)
    set_selected_flow(ctx, "flow1")

    assert not check_profile_gate_pending(ctx)

    ctx.mark_done("optimal_questions")
    state = ctx.read_json("understanding/analysis_state.json")
    state["themes"] = [{"id": "t1", "label": "Theme", "summary": "Summary text"}]
    state["narrative"] = {"thesis": "Core thesis from the interview."}
    state["interview_identity"] = {"one_line_summary": "A conversation about testing."}
    state["completion"] = {"analysis_ready": True, "blockers": []}
    ctx.write_json("understanding/analysis_state.json", state, skip_handoff=True)

    assert check_profile_gate_pending(ctx)


def test_empty_speakers_json_does_not_trigger_handoff(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    ctx.path("understanding/speakers.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/speakers.json").write_text("{}", encoding="utf-8")
    ctx.mark_done("speaker_roles")
    assert pending_handoff_stage(ctx) is None


def test_complete_speakers_triggers_handoff(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    ctx.write_json("understanding/speakers.json", COMPLETE_SPEAKERS, stage_key="speaker_roles")
    ctx.mark_done("speaker_roles")
    assert pending_handoff_stage(ctx) == "speaker_roles"
    assert artifact_ready_for_review("understanding/speakers.json", ctx)
