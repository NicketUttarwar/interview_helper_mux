"""Zero-shot flow: verify checkpoints only after artifacts are populated."""

from __future__ import annotations

import pytest

from interview_mux.analysis_memory import ensure_analysis_workspace
from interview_mux.artifact_completeness import (
    analysis_profile_ready_for_review,
    artifact_ready_for_review,
)
from interview_mux.gates import (
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    is_operator_profile_verified,
)
from interview_mux.run_context import RunContext
from interview_mux.web.server import _build_stage_list
from run_fixtures import init_run_meta_for_test, patch_executions_root, seed_analysis_ready_artifacts

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
        check_g1_vo(ctx),
        check_transcript_review_pending(ctx),
        is_operator_profile_verified(ctx),
        check_profile_gate_pending(ctx),
    )
    return next(s["status"] for s in stages if s["id"] == stage_id)

def test_fresh_run_analysis_profile_locked(tmp_path, monkeypatch) -> None:
    from interview_mux.v2.config import v2_enabled

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    init_run_meta_for_test(ctx)
    ensure_analysis_workspace(ctx)

    if v2_enabled():
        # Profile gate cut in v2 — stage is not in the operator linear path.
        assert "analysis_profile" not in {s["id"] for s in _build_stage_list(
            ctx,
            check_g1_vo(ctx),
            check_transcript_review_pending(ctx),
            is_operator_profile_verified(ctx),
            check_profile_gate_pending(ctx),
        )}
        assert not analysis_profile_ready_for_review(ctx)
        return

    assert _stage_status(ctx, "analysis_profile") == "locked"
    assert not analysis_profile_ready_for_review(ctx)
    meta = ctx.read_json("run_meta.json")
    assert not meta.get("handoff_pending_writes")

def test_analysis_profile_action_required_after_analysis(tmp_path, monkeypatch) -> None:
    from interview_mux.v2.config import v2_enabled

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    init_run_meta_for_test(ctx)
    ensure_analysis_workspace(ctx)
    seed_analysis_ready_artifacts(ctx)

    assert analysis_profile_ready_for_review(ctx)
    if v2_enabled():
        assert not check_profile_gate_pending(ctx)
        return
    assert _stage_status(ctx, "analysis_profile") == "action_required"

def test_profile_gate_pending_requires_populated_profile(tmp_path, monkeypatch) -> None:
    from interview_mux.v2.config import v2_enabled

    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    init_run_meta_for_test(ctx)
    ensure_analysis_workspace(ctx)

    assert not check_profile_gate_pending(ctx)

    seed_analysis_ready_artifacts(ctx)

    if v2_enabled():
        assert not check_profile_gate_pending(ctx)
        return
    assert check_profile_gate_pending(ctx)

def test_empty_speakers_json_no_handoff_pause_v2(tmp_path, monkeypatch) -> None:
    """v2: handoffs removed — empty speakers never pauses for handoff."""
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    ctx.path("understanding/speakers.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("understanding/speakers.json").write_text("{}", encoding="utf-8")
    ctx.mark_done("speaker_roles")
    assert not artifact_ready_for_review("understanding/speakers.json", ctx)

def test_complete_speakers_ready_for_review_v2(tmp_path, monkeypatch) -> None:
    """v2: complete speakers artifact is review-ready without handoff pause."""
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext(create=True)
    ctx.write_json("understanding/speakers.json", COMPLETE_SPEAKERS, stage_key="speaker_roles")
    ctx.mark_done("speaker_roles")
    assert artifact_ready_for_review("understanding/speakers.json", ctx)
