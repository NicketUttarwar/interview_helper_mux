from __future__ import annotations

import pytest

from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    StageArtifactsIncompleteError,
    assert_stage_artifacts_complete,
    reconcile_stage_done_marker,
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
