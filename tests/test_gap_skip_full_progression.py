"""Gap-fill skip path — profile gate, analysis_complete, and delivery unlock."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_completeness import analysis_profile_ready_for_review
from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
from interview_mux.pipeline import (
    ANALYSIS_ORDER,
    maybe_finalize_shared_analysis,
    shared_analysis_chain_complete,
)
from interview_mux.progression_readiness import build_delivery_readiness_report
from interview_mux.stages.gaps import ensure_gap_fill_skipped
from run_fixtures import (
    isolated_run_ctx,
    minimal_content_brief,
    minimal_manifest,
    minimal_speakers,
    patch_merged_config,
    populated_analysis_state,
    sound_design_plan_with,
)


def _seed_through_sound_design_palettes(ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    write_validated_artifact(
        ctx,
        "understanding/speakers.json",
        {
            **minimal_speakers(),
            "conversation_profile": {
                "format_class_candidate": "one_on_one",
                "tone_class_candidate": "journalistic",
            },
        },
        merge_from_disk=False,
        stage_key="speaker_roles",
    )
    write_validated_artifact(
        ctx,
        "understanding/content_brief.json",
        minimal_content_brief(),
        merge_from_disk=False,
        stage_key="content_brief_reanchor",
    )
    write_validated_artifact(
        ctx,
        "segments/manifest.json",
        minimal_manifest("seg_001", "seg_002"),
        merge_from_disk=False,
        stage_key="segment_classification",
    )
    write_validated_artifact(
        ctx,
        "understanding/sound_design_plan.json",
        sound_design_plan_with(),
        merge_from_disk=False,
        stage_key="sound_design_palettes",
    )
    for sid in ANALYSIS_ORDER:
        if sid in ("missing_framing", "optimal_questions", "delivery_brief_build", "soundscape_policy_build", "episode_structure_compose"):
            continue
        ctx.mark_done(sid, force=True)


def test_gap_skip_unlocks_profile_and_delivery_after_episode_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.analysis_memory import update_completion_from_analysis
    from run_fixtures import seed_analysis_ready_artifacts

    ctx = isolated_run_ctx(tmp_path, "gap_skip_full")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    seed_analysis_ready_artifacts(ctx, verified=False)
    ensure_gap_fill_skipped(ctx, reason="operator skip", signals={"reseed": True})
    for sid in ("delivery_brief_build", "soundscape_policy_build", "episode_structure_compose"):
        ctx.mark_done(sid, force=True)

    update_completion_from_analysis(ctx)
    assert analysis_profile_ready_for_review(ctx)
    assert maybe_finalize_shared_analysis(ctx)
    assert ctx.artifact_exists("analysis_complete.json")

    verified = populated_analysis_state(ctx.run_id, verified=True)
    write_validated_artifact(
        ctx,
        "understanding/analysis_state.json",
        verified,
        merge_from_disk=False,
        stage_key="analysis_profile",
    )

    report = build_delivery_readiness_report(ctx, target_stage="topic_coverage_audit")
    blocker_ids = {b.get("id") for b in report.get("blockers") or []}
    assert "g1_vo_pickup" not in blocker_ids
    assert "analysis_complete" not in blocker_ids


def test_maybe_finalize_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "gap_finalize_idempotent")
    _seed_through_sound_design_palettes(ctx, monkeypatch)
    ensure_gap_fill_skipped(ctx, reason="test", signals={})
    for sid in (
        "delivery_brief_build",
        "soundscape_policy_build",
        "episode_structure_compose",
    ):
        ctx.mark_done(sid, force=True)

    assert maybe_finalize_shared_analysis(ctx)
    assert ctx.artifact_exists("analysis_complete.json")
    assert maybe_finalize_shared_analysis(ctx)
