from __future__ import annotations

import pytest

from interview_mux.gates import (
    check_g1_vo,
    check_transcript_review_pending,
    check_profile_gate_pending,
    is_operator_profile_verified,
    require_flow1_extended_gates,
    require_profile_verified_for_flow1_extended,
    require_selected_flow_flow2,
    set_selected_flow,
)
from interview_mux.analysis_memory import default_analysis_state
from interview_mux.run_context import RunContext
from run_fixtures import ctx_from_fixture, isolated_run_ctx


def _write_analysis_state(ctx: RunContext, *, verified: bool) -> None:
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    state = default_analysis_state(ctx.run_id)
    state["meta"]["operator_verified"] = verified
    ctx.write_json("understanding/analysis_state.json", state)


def test_profile_gate_pending_only_for_flow1_unverified(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_001")
    set_selected_flow(ctx, "flow1")
    _write_analysis_state(ctx, verified=False)
    assert check_profile_gate_pending(ctx) is True
    _write_analysis_state(ctx, verified=True)
    assert check_profile_gate_pending(ctx) is False


def test_profile_gate_skipped_after_topic_coverage_done(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_002")
    set_selected_flow(ctx, "flow1")
    _write_analysis_state(ctx, verified=False)
    ctx.mark_done("topic_coverage_audit")
    assert check_profile_gate_pending(ctx) is False


def test_require_profile_verified_raises_and_logs(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_003")
    set_selected_flow(ctx, "flow1")
    _write_analysis_state(ctx, verified=False)
    with pytest.raises(SystemExit, match="Profile gate"):
        require_profile_verified_for_flow1_extended(ctx)
    log_path = ctx.path("gui_log.jsonl")
    assert log_path.is_file()
    assert "Profile gate" in log_path.read_text(encoding="utf-8")


def test_flow1_extended_requires_selected_flow_flow1(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_004")
    _write_analysis_state(ctx, verified=True)
    set_selected_flow(ctx, "flow2")
    with pytest.raises(SystemExit, match="selected_flow=flow1"):
        require_flow1_extended_gates(ctx)


def test_is_operator_profile_verified_missing_state(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_005")
    assert is_operator_profile_verified(ctx) is False


def test_flow2_requires_selected_flow_flow2(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_006")
    set_selected_flow(ctx, "flow1")
    with pytest.raises(SystemExit, match="selected_flow=flow2"):
        require_selected_flow_flow2(ctx)


def test_set_selected_flow_preserves_existing_run_meta(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_007")
    ctx.write_json(
        "run_meta.json",
        {
            "input_audio_path": "ASSETS/input/demo.wav",
            "audio_preclean": {"enabled": True, "scope": "vo_pickup"},
        },
    )
    set_selected_flow(ctx, "flow3")
    meta = ctx.read_json("run_meta.json")
    assert meta["selected_flow"] == "flow3"
    assert meta["input_audio_path"] == "ASSETS/input/demo.wav"
    assert meta["audio_preclean"]["scope"] == "vo_pickup"


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
