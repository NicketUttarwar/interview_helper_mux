from __future__ import annotations

import pytest

from interview_mux.gates import (
    check_g1_vo,
    check_transcript_review_pending,
    check_profile_gate_pending,
    is_operator_profile_verified,
    require_analysis_artifacts_complete,
    require_delivery_gates,
    require_profile_verified_for_delivery,
)
from run_fixtures import patch_merged_config
from interview_mux.analysis_memory import default_analysis_state
from interview_mux.run_context import RunContext
from run_fixtures import ctx_from_fixture, isolated_run_ctx, seed_analysis_ready_artifacts


def _write_analysis_state(ctx: RunContext, *, verified: bool) -> None:
    seed_analysis_ready_artifacts(ctx, verified=verified)


def test_profile_gate_removed_in_v2(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_001")
    _write_analysis_state(ctx, verified=False)
    require_profile_verified_for_delivery(ctx)
    require_delivery_gates(ctx)
    require_analysis_artifacts_complete(ctx)


def test_v2_g1_clear_is_nonblocking(tmp_path, monkeypatch):
    monkeypatch.setattr("interview_mux.v2.config.v2_g1_optional", lambda: True)
    ctx = isolated_run_ctx(tmp_path, "run_v2_g1")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "L1",
                    "delivery": "record",
                    "blocking": True,
                    "severity": "high",
                    "targets_segment_id": "seg_1",
                    "gap_type": "missing_framing",
                    "text": "Can you expand on that?",
                    "placement": "after",
                }
            ]
        },
    )
    from interview_mux.gates import require_g1_clear

    require_g1_clear(ctx)


def test_is_operator_profile_verified_missing_state(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_005")
    assert is_operator_profile_verified(ctx) is False


def test_check_transcript_review_pending_clears_after_done_marker(tmp_path):
    ctx = ctx_from_fixture(tmp_path)
    assert check_transcript_review_pending(ctx) is True
    ctx.mark_done("transcript_review")
    assert check_transcript_review_pending(ctx) is False


def test_check_g1_vo_accepts_line_id_or_segment_id_wav(tmp_path):
    ctx = ctx_from_fixture(tmp_path, run_id="exec_g1_smoke")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "targets_segment_id": "seg_001",
                    "delivery": "record",
                    "gap_type": "context",
                    "text": "Add context",
                    "placement": "before",
                }
            ]
        },
    )
    assert check_g1_vo(ctx) == ["line_001"]

    pickup_dir = ctx.path("vo_pickup")
    pickup_dir.mkdir(parents=True, exist_ok=True)
    (pickup_dir / "line_001.wav").touch()
    assert check_g1_vo(ctx) == []

    (pickup_dir / "line_001.wav").unlink()
    (pickup_dir / "seg_001.wav").touch()
    assert check_g1_vo(ctx) == []


def test_require_analysis_artifacts_complete_noop_in_v2(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_artifacts_gate")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx.mark_done("optimal_questions")
    require_analysis_artifacts_complete(ctx)
