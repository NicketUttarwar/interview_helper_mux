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
    mark_done_raw,
    minimal_content_brief,
    minimal_manifest,
    minimal_speakers,
    patch_merged_config,
    plant_primary_and_stamp,
    populated_analysis_state,
    seed_analysis_ready_artifacts,
    sound_design_plan_with,
    write_fixture_json,
)

_MINIMAL_EPISODE_STRUCTURE = {
    "schema_version": 1,
    "policy_hash": "fixture",
    "axes": {"format_class": "one_on_one", "tone_class": "journalistic", "atlas_bucket": "one_on_one"},
    "slot_plan": [
        {
            "slot_id": "slot_open",
            "component_id": "open",
            "class": "standard",
            "gate": "must",
        }
    ],
    "segment_order": ["seg_001"],
    "hook_reel": {"segment_id": "seg_001", "repeat_allowed": False},
    "omit_reasons": [],
    "rationale": ["fixture"],
    "integrity": {"ok": True, "flags": []},
    "occupancy": {"violations": []},
}


def _plant_analysis_through_episode(ctx, *, gap_compose_done: bool = True) -> None:
    from interview_mux.v2.config import ANALYSIS_ORDER

    seed_analysis_ready_artifacts(ctx, verified=False)
    for sid in ANALYSIS_ORDER:
        plant_primary_and_stamp(ctx, sid)
        if sid == "episode_structure_compose":
            break
    seed_analysis_ready_artifacts(ctx, verified=False)
    write_fixture_json(ctx, "understanding/episode_structure.json", _MINIMAL_EPISODE_STRUCTURE)
    brief = ctx.read_json("understanding/content_brief.json")
    if isinstance(brief, dict):
        for topic in brief.get("topics") or []:
            if isinstance(topic, dict) and not topic.get("segment_ids"):
                topic["segment_ids"] = ["seg_001"]
        write_fixture_json(ctx, "understanding/content_brief.json", brief)
    script = ctx.final_path("understanding", "interviewer_script.txt")
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# fixture interviewer script\n", encoding="utf-8")
    mark_done_raw(ctx, "episode_structure_compose")
    if gap_compose_done:
        mark_done_raw(ctx, "gap_framing_compose", "optimal_questions")
    else:
        for sid in ("gap_framing_compose", "optimal_questions"):
            done = ctx.final_path(".stage_done", sid)
            if done.is_file():
                done.unlink()


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
        mark_done_raw(ctx, sid)


def test_gap_skip_unlocks_profile_and_delivery_after_episode_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.analysis_memory import update_completion_from_analysis

    ctx = isolated_run_ctx(tmp_path, "gap_skip_full")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    _plant_analysis_through_episode(ctx, gap_compose_done=True)
    ensure_gap_fill_skipped(ctx, reason="operator skip", signals={"reseed": True})

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
    _plant_analysis_through_episode(ctx, gap_compose_done=True)
    ensure_gap_fill_skipped(ctx, reason="test", signals={})

    assert maybe_finalize_shared_analysis(ctx)
    assert ctx.artifact_exists("analysis_complete.json")
    assert maybe_finalize_shared_analysis(ctx)


def test_maybe_finalize_withholds_when_gap_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ESC-B1: do not stamp analysis_complete while gap compose is still pending."""
    from interview_mux.stages.gaps import gap_compose_stage_done

    ctx = isolated_run_ctx(tmp_path, "gap_finalize_withhold")
    ctx.write_json(
        "run_meta.json",
        {"gap_framing_enabled": True, "gap_fill_mode": "active"},
        skip_handoff=True,
    )
    _plant_analysis_through_episode(ctx, gap_compose_done=False)

    assert shared_analysis_chain_complete(ctx)
    assert not gap_fill_was_skipped(ctx)
    assert not gap_compose_stage_done(ctx)
    assert maybe_finalize_shared_analysis(ctx) is False
    assert not ctx.artifact_exists("analysis_complete.json")
