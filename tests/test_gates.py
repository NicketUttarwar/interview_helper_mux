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


def test_check_g1_vo_accepts_line_id_or_segment_id_wav(tmp_path, monkeypatch):
    import wave

    monkeypatch.setattr(
        "interview_mux.vo_speech_qa.vo_passes_speech_qa",
        lambda *_a, **_k: True,
    )
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

    def _write_wav(path):
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(48_000)
            handle.writeframes(b"\x00\x00" * 4800)

    _write_wav(pickup_dir / "line_001.wav")
    assert check_g1_vo(ctx) == []

    (pickup_dir / "line_001.wav").unlink()
    _write_wav(pickup_dir / "seg_001.wav")
    assert check_g1_vo(ctx) == []


def test_check_g1_vo_stale_synthesize_wav_still_missing(tmp_path, monkeypatch):
    import wave

    from interview_mux.vo_synthesis_audit import record_synthesis

    monkeypatch.setattr(
        "interview_mux.vo_speech_qa.vo_passes_speech_qa",
        lambda *_a, **_k: True,
    )
    ctx = isolated_run_ctx(tmp_path, "run_g1_stale")
    line = {
        "line_id": "vo_ori_001",
        "targets_segment_id": "seg_001",
        "delivery": "synthesize",
        "gap_type": "opening_orientation",
        "text": "Today we talk about food science.",
        "placement": "before",
    }
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": [line]})
    synth_dir = ctx.path("vo_pickup") / "synthesized"
    synth_dir.mkdir(parents=True, exist_ok=True)
    out = synth_dir / "vo_ori_001.wav"
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 4800)
    stale = dict(line)
    stale["text"] = "Old orientation copy that no longer matches."
    record_synthesis(ctx, stale, backend="mlx_audio", out_wav=out)
    # Raw WAV exists but resolve rejects stale script_hash → still missing for G1.
    assert (ctx.path("vo_pickup") / "synthesized" / "vo_ori_001.wav").is_file()
    assert check_g1_vo(ctx) == ["vo_ori_001"]


def test_require_analysis_artifacts_complete_noop_in_v2(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_artifacts_gate")
    patch_merged_config(monkeypatch, {"analysis": {"flow_hardening": {"enabled": True}}})
    ctx.mark_done("optimal_questions")
    require_analysis_artifacts_complete(ctx)
