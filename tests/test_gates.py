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


def test_profile_gate_pending_only_for_flow1_unverified(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_001")
    _write_analysis_state(ctx, verified=False)
    assert check_profile_gate_pending(ctx) is True
    _write_analysis_state(ctx, verified=True)
    assert check_profile_gate_pending(ctx) is False


def test_profile_gate_skipped_after_topic_coverage_done(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_002")
    _write_analysis_state(ctx, verified=False)
    ctx.mark_done("topic_coverage_audit", force=True)
    assert check_profile_gate_pending(ctx) is False


def test_require_profile_verified_raises_and_logs(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_003")
    _write_analysis_state(ctx, verified=False)
    with pytest.raises(SystemExit, match="Profile gate"):
        require_profile_verified_for_delivery(ctx)
    log_path = ctx.path("gui_log.jsonl")
    assert log_path.is_file()
    assert "Profile gate" in log_path.read_text(encoding="utf-8")


def test_delivery_gates_require_profile_verified(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_004")
    _write_analysis_state(ctx, verified=False)
    with pytest.raises(SystemExit, match="Profile gate"):
        require_delivery_gates(ctx)


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


def test_require_analysis_artifacts_complete_raises_when_incomplete(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_artifacts_gate")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx.mark_done("optimal_questions")
    with pytest.raises(SystemExit, match="Analysis artifacts gate"):
        require_analysis_artifacts_complete(ctx)
