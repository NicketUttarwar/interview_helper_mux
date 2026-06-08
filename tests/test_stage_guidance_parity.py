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
