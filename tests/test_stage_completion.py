from __future__ import annotations

import json

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
from run_fixtures import mark_done_raw
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
    # Production mark_done must refuse partial resilience even with force.
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
    from interview_mux.write_staging import exit_stage_staging

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    ctx = RunContext(create=True)
    enter_stage_staging("speaker_roles")
    try:
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
    finally:
        exit_stage_staging()


def test_staged_partial_speakers_blocked_for_critical_stage(tmp_path, monkeypatch):
    """Critical stages never approve resilience-partial staging (A/C)."""
    from interview_mux.analysis_memory import default_analysis_state
    from interview_mux.write_staging import exit_stage_staging

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    ctx = RunContext(create=True)
    enter_stage_staging("speaker_roles")
    try:
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
    finally:
        exit_stage_staging()


def test_all_pending_stages_excludes_save_blocked(tmp_path, monkeypatch):
    from interview_mux.write_staging import exit_stage_staging

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled",
        lambda: True,
    )
    ctx = RunContext(create=True)
    enter_stage_staging("speaker_roles")
    try:
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
    finally:
        exit_stage_staging()


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
    mark_done_raw(ctx, "content_context")
    mark_done_raw(ctx, "content_brief_reanchor")

    assert stage_artifact_incompleteness(ctx, "content_context") is None
    reconcile_stage_done_marker(ctx, "content_context")
    assert ctx.is_done("content_context")

    assert stage_artifact_incompleteness(ctx, "content_brief_reanchor") is not None
    reconcile_stage_done_marker(ctx, "content_brief_reanchor")
    assert not ctx.is_done("content_brief_reanchor")


def test_staged_empty_optimal_questions_acceptable_when_all_self_explanatory(
    tmp_path, monkeypatch
):
    from interview_mux.write_staging import exit_stage_staging

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
    try:
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
    finally:
        exit_stage_staging()


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


def test_gap_fill_skip_stub_incomplete_when_framing_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"gap_framing_enabled": True, "gap_fill_mode": "active"},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [],
            "gaps": [],
            "_meta": {"producer": "gap_fill_skip", "producer_stage": "optimal_questions"},
        },
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, "gap_framing_compose")
    assert reason and "skip stub" in reason


def test_gfc_b2_zero_line_compose_incomplete_when_framing_yes(tmp_path, monkeypatch):
    """CSP-05 / GFC-B2: framing Yes + zero compose lines → incomplete (not soft-done)."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_research.research_shape_core_thin",
        lambda _ctx: False,
    )
    ctx = RunContext(create=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [],
            "gaps": [],
            "_meta": {
                "producer": "gap_framing_compose",
                "producer_stage": "gap_framing_compose",
            },
        },
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, "gap_framing_compose")
    assert reason and "zero interviewer_lines" in reason
    assert "OpenAI primary" in reason or "framing Yes" in reason


def test_stale_required_artifact_is_incomplete(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    path = ctx.final_path("understanding", "sound_design_plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "_meta": {
                    "producer_stage": "sound_design_plan",
                    "stale": True,
                    "stale_reason": "invalidated_by:nugget_layup_compose",
                },
            }
        )
        + "\n"
    )
    reason = stage_artifact_incompleteness(ctx, "sound_design_plan")
    assert reason and (
        "marked stale" in reason or "stale_meta" in reason or "stale" in reason
    )


def test_mmaudio_incomplete_when_sdp_wavs_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    wav = ctx.final_path("master", "assembly_preview.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF")
    qa = ctx.final_path("sound_design", "mmaudio_qa.json")
    qa.parent.mkdir(parents=True, exist_ok=True)
    qa.write_text(
        json.dumps(
            {
                "status": "complete",
                "assets": [
                    {
                        "asset_id": "a",
                        "path": "sound_design/assets/a.wav",
                        "verdict": "pass",
                        "duration_s": 1.0,
                    }
                ],
            }
        )
        + "\n"
    )
    monkeypatch.setattr(
        "interview_mux.stage_completion.artifact_status_for_stage",
        lambda path, _ctx, _sid: "complete" if "mmaudio_qa" in path else "pending",
    )
    monkeypatch.setattr(
        "interview_mux.sdp_cross_validate.missing_sdp_asset_wavs",
        lambda _ctx: ["theme_missing_bed"],
    )
    reason = stage_artifact_incompleteness(ctx, "mmaudio_sfx")
    assert reason and "theme_missing_bed" in reason
    mark_done_raw(ctx, "mmaudio_sfx")
    assert not reconcile_stage_done_marker(ctx, "mmaudio_sfx")
    assert not ctx.is_done("mmaudio_sfx")

