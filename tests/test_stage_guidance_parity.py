"""Stage guidance registry parity — every GUI stage must expose operator guidance."""

from __future__ import annotations

import pytest

from interview_mux.gates import (
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    is_operator_profile_verified,
)
from interview_mux.journey_state import OPERATOR_PHASES
from interview_mux.stage_guidance import (
    G0_LOCKED_ANALYSIS_STAGES,
    STAGE_UNLOCKS,
    build_phase_guidance,
    build_stage_guidance,
    guidance_required_stage_ids,
)
from interview_mux.web.server import _build_stage_list
from interview_mux.web.stages import STAGE_BY_ID
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def test_stage_unlocks_covers_stage_by_id() -> None:
    missing = set(STAGE_BY_ID) - set(STAGE_UNLOCKS)
    assert not missing, f"Add STAGE_UNLOCKS for: {sorted(missing)}"


def test_guidance_required_matches_stage_by_id() -> None:
    assert guidance_required_stage_ids() == frozenset(STAGE_BY_ID.keys())


def test_build_stage_guidance_has_unlocks_and_items(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "guidance_smoke")
    init_run_meta_for_test(ctx)
    for stage_id in STAGE_BY_ID:
        guidance = build_stage_guidance(ctx, stage_id, status="pending")
        assert guidance["unlocks"], stage_id
        assert guidance["prerequisites"] or guidance["actions"], stage_id
        assert guidance["phase_label"]


def test_g0_locks_source_acoustic_profile(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "g0_lock")
    init_run_meta_for_test(ctx)
    ctx.write_json("transcript/review_queue.json", {"chunks": []})
    assert check_transcript_review_pending(ctx)

    stages = _build_stage_list(
        ctx,
        None,
        check_g1_vo(ctx),
        True,
        is_operator_profile_verified(ctx),
        check_profile_gate_pending(ctx),
    )
    sap = next(s for s in stages if s["id"] == "source_acoustic_profile")
    assert sap["status"] == "locked"
    assert sap["guidance"]["prerequisites"][0]["status"] == "todo"
    assert "transcript review" in sap["guidance"]["prerequisites"][0]["label"].lower()


def test_g0_locked_analysis_stages_includes_source_acoustic_profile() -> None:
    assert "source_acoustic_profile" in G0_LOCKED_ANALYSIS_STAGES
    assert "speaker_roles" in G0_LOCKED_ANALYSIS_STAGES
    assert "ingest" not in G0_LOCKED_ANALYSIS_STAGES


def test_phase_guidance_includes_all_phases(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "phase_guidance")
    init_run_meta_for_test(ctx)
    stages = _build_stage_list(
        ctx,
        None,
        check_g1_vo(ctx),
        check_transcript_review_pending(ctx),
        is_operator_profile_verified(ctx),
        check_profile_gate_pending(ctx),
    )
    phase_guidance = build_phase_guidance(ctx, stages)
    assert "start" in phase_guidance
    for phase in OPERATOR_PHASES:
        assert phase in phase_guidance
        assert phase_guidance[phase]["goal"]


def test_flow_stage_shows_analysis_artifacts_gate_when_incomplete(tmp_path, monkeypatch) -> None:
    from run_fixtures import patch_merged_config

    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx = isolated_run_ctx(tmp_path, "gate_incomplete")
    init_run_meta_for_test(ctx)
    guidance = build_stage_guidance(ctx, "topic_coverage_audit", status="pending", flow="flow1")
    labels = [p["label"] for p in guidance["prerequisites"]]
    assert any("Analysis artifacts complete" in label for label in labels)
    assert any(p["label"].startswith("Analysis artifacts complete") and p["status"] == "todo" for p in guidance["prerequisites"])


def test_flow_stage_shows_analysis_artifacts_gate_done_when_ready(tmp_path, monkeypatch) -> None:
    from run_fixtures import patch_merged_config, seed_analysis_ready_artifacts

    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx = isolated_run_ctx(tmp_path, "gate_ready")
    init_run_meta_for_test(ctx)
    seed_analysis_ready_artifacts(ctx, verified=True)
    guidance = build_stage_guidance(ctx, "topic_coverage_audit", status="pending", flow="flow1")
    gate_items = [p for p in guidance["prerequisites"] if p.get("id") == "analysis_artifacts"]
    assert gate_items
    assert gate_items[0]["status"] == "done"


def test_guidance_todo_items_have_stable_ids(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "guidance_ids")
    init_run_meta_for_test(ctx)
    for stage_id in STAGE_BY_ID:
        guidance = build_stage_guidance(ctx, stage_id, status="pending")
        for bucket in ("prerequisites", "actions"):
            for item in guidance.get(bucket) or []:
                if item.get("status") == "todo":
                    assert item.get("id"), f"{stage_id}.{bucket} missing id: {item.get('label')}"
                    assert item.get("label"), f"{stage_id}.{bucket} missing label for id={item.get('id')}"


def test_non_done_stages_have_actionable_guidance(tmp_path) -> None:
    """Every pending stage exposes ≥1 todo item or waiting prerequisite."""
    ctx = isolated_run_ctx(tmp_path, "actionable_substeps")
    init_run_meta_for_test(ctx)
    gate_action_stages = frozenset(
        {
            "transcript_review",
            "disfluency_review",
            "analysis_profile",
            "g1_vo_pickup",
            "g2_flow_select",
        }
    )
    for stage_id in STAGE_BY_ID:
        for status in ("pending", "action_required"):
            if status == "action_required" and stage_id not in gate_action_stages:
                continue
            guidance = build_stage_guidance(ctx, stage_id, status=status)
            items = list(guidance.get("prerequisites") or []) + list(guidance.get("actions") or [])
            todos = [i for i in items if i.get("status") == "todo"]
            waiting = [i for i in items if i.get("status") == "waiting"]
            artifact_waiting = [
                c for c in guidance.get("artifact_checks") or [] if c.get("status") == "waiting"
            ]
            assert todos or waiting or artifact_waiting, (
                f"{stage_id} status={status} has no actionable guidance"
            )
