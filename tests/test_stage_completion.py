from __future__ import annotations

import pytest

from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    StageArtifactsIncompleteError,
    assert_stage_artifacts_complete,
    reconcile_stage_done_marker,
    stage_artifact_incompleteness,
    staged_artifacts_acceptable,
)
from interview_mux.write_staging import (
    WriteApprovalBlockedError,
    assert_write_approval_allowed,
    enter_stage_staging,
    write_pending_content,
)


def test_reconcile_clears_stage_done_for_partial_resilience(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    write_validated_artifact(
        ctx,
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.8},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.7},
            ],
            "_meta": {"resilience": {"partial": True}},
        },
        merge_from_disk=False,
        stage_key="speaker_roles",
    )
    ctx.mark_done("speaker_roles", force=True)
    assert not ctx.is_done("speaker_roles")
    marker = ctx.final_path(".stage_done", "speaker_roles")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    assert ctx.is_done("speaker_roles")
    reconcile_stage_done_marker(ctx, "speaker_roles")
    assert not ctx.is_done("speaker_roles")


def test_assert_stage_artifacts_complete_raises_for_partial(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    write_validated_artifact(
        ctx,
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.8},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.7},
            ],
            "_meta": {"resilience": {"partial": True}},
        },
        merge_from_disk=False,
        stage_key="speaker_roles",
    )
    with pytest.raises(StageArtifactsIncompleteError):
        assert_stage_artifacts_complete(ctx, "speaker_roles")


def test_staged_partial_blocked_from_write_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    ctx = RunContext(create=True)
    enter_stage_staging("speaker_roles")
    write_pending_content(
        ctx,
        "speaker_roles",
        "understanding/speakers.json",
        data={
            "speakers": [
                {"speaker_id": "spk_0", "role": "unknown", "confidence": 0.8},
                {"speaker_id": "spk_1", "role": "unknown", "confidence": 0.7},
            ],
            "_meta": {"resilience": {"partial": True}},
        },
    )
    ok, reason = staged_artifacts_acceptable(ctx, "speaker_roles")
    assert not ok
    assert "partial" in reason.lower()
    with pytest.raises(WriteApprovalBlockedError):
        assert_write_approval_allowed(ctx, "speaker_roles")


def test_staged_partial_speakers_blocked_for_critical_stage(tmp_path, monkeypatch):
    """Critical stages never approve resilience-partial staging (A/C)."""
    from interview_mux.analysis_memory import default_analysis_state

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    ctx = RunContext(create=True)
    enter_stage_staging("speaker_roles")
    speakers = {
        "speakers": [
            {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.8},
            {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.7},
        ],
        "_meta": {"resilience": {"partial": True}},
    }
    write_pending_content(ctx, "speaker_roles", "understanding/speakers.json", data=speakers)
    state = default_analysis_state(ctx.run_id)
    state["speakers"] = speakers["speakers"]
    write_pending_content(ctx, "speaker_roles", "understanding/analysis_state.json", data=state)
    ok, reason = staged_artifacts_acceptable(ctx, "speaker_roles")
    assert not ok
    assert "partial" in reason.lower()


def test_all_pending_stages_excludes_save_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    ctx = RunContext(create=True)
    enter_stage_staging("speaker_roles")
    write_pending_content(
        ctx,
        "speaker_roles",
        "understanding/speakers.json",
        data={
            "speakers": [
                {"speaker_id": "spk_0", "role": "unknown", "confidence": 0.8},
            ],
            "_meta": {"resilience": {"partial": True}},
        },
    )
    from interview_mux.write_staging import all_pending_stages

    assert all_pending_stages(ctx, savable_only=False) == ["speaker_roles"]
    assert all_pending_stages(ctx) == []


def test_content_context_stays_done_when_only_reanchor_gaps(tmp_path, monkeypatch):
    """Re-anchor segment gaps must not invalidate an already-complete content_context."""
    import json
    from pathlib import Path

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    fixture = Path(__file__).resolve().parent / "fixtures/sufficiency/content_context/pass.json"
    brief = json.loads(fixture.read_text())
    brief["topics"].append(
        {
            "name": "Topic two",
            "summary": "Another summary with enough detail for validation.",
            "segment_ids": [],
            "confidence": 0.8,
        }
    )
    brief["topic_relationships"] = []
    write_validated_artifact(
        ctx,
        "understanding/content_brief.json",
        brief,
        merge_from_disk=False,
        stage_key="content_context",
    )
    ctx.mark_done("content_context", force=True)
    ctx.mark_done("content_brief_reanchor", force=True)

    assert stage_artifact_incompleteness(ctx, "content_context") is None
    reconcile_stage_done_marker(ctx, "content_context")
    assert ctx.is_done("content_context")

    assert stage_artifact_incompleteness(ctx, "content_brief_reanchor") is not None
    reconcile_stage_done_marker(ctx, "content_brief_reanchor")
    assert not ctx.is_done("content_brief_reanchor")


def test_staged_empty_optimal_questions_acceptable_when_all_self_explanatory(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    ctx = RunContext(create=True)
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_001",
                    "self_explanatory": True,
                    "gap_type": "ok_with_light_bridge",
                    "severity": "low",
                }
            ]
        },
        skip_handoff=True,
    )
    enter_stage_staging("optimal_questions")
    write_pending_content(
        ctx,
        "optimal_questions",
        "understanding/gap_report.json",
        data={
            "interviewer_lines": [],
            "_meta": {"resilience": {"partial": True}},
        },
    )
    ok, reason = staged_artifacts_acceptable(ctx, "optimal_questions")
    assert ok, reason
    assert_write_approval_allowed(ctx, "optimal_questions")


def test_assert_stage_artifacts_complete_requires_interviewer_script(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    write_validated_artifact(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        merge_from_disk=False,
        stage_key="optimal_questions",
    )
    reason = stage_artifact_incompleteness(ctx, "optimal_questions")
    assert reason == "understanding/interviewer_script.txt is pending"
    with pytest.raises(StageArtifactsIncompleteError, match="interviewer_script"):
        assert_stage_artifacts_complete(ctx, "optimal_questions")
