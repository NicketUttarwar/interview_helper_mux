from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from interview_mux.disfluency.context import attach_disfluency_context, disfluency_summary_for_ctx
from interview_mux.run_context import RunContext
from interview_mux.sound_design import _disfluency_excluded_windows, _overlaps_excluded, mix
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_disfluency_excluded_windows_from_edl() -> None:
    edl = {
        "clips": [
            {"type": "speech", "timeline_start_ms": 0, "duration_ms": 5000},
            {"type": "disfluency", "timeline_start_ms": 5000, "duration_ms": 300},
            {"type": "speech", "timeline_start_ms": 5300, "duration_ms": 4700},
        ]
    }
    windows = _disfluency_excluded_windows(edl)
    assert windows == [(5000, 5300)]


def test_overlaps_excluded_detects_overlap() -> None:
    assert _overlaps_excluded(5100, 200, [(5000, 5300)]) is True
    assert _overlaps_excluded(6000, 200, [(5000, 5300)]) is False


def test_disfluency_summary_for_ctx(tmp_path: Path, monkeypatch) -> None:
    cfg = {"disfluency_extract": {"enabled": True}}
    patch_merged_config(monkeypatch, cfg)
    ctx = isolated_run_ctx(tmp_path, "run_sum")
    ctx.write_json(
        "transcript/disfluencies.json",
        {
            "schema_version": 1,
            "status": "ready",
            "events": [
                {
                    "event_id": "fill_0001",
                    "start_ms": 100,
                    "end_ms": 400,
                    "text": "um",
                    "review_status": "confirmed",
                    "include_in_restore": True,
                }
            ],
            "stats": {"total": 1, "confirmed": 1, "pending": 0, "rejected": 0},
        },
    )
    ctx.mark_done("disfluency_review")
    summary = disfluency_summary_for_ctx(ctx)
    assert summary is not None
    assert summary["confirmed_count"] == 1
    assert summary["restore_eligible_count"] == 1


def test_attach_disfluency_context_injects_key(tmp_path: Path, monkeypatch) -> None:
    cfg = {"disfluency_extract": {"enabled": True}}
    patch_merged_config(monkeypatch, cfg)
    ctx = isolated_run_ctx(tmp_path, "run_attach")
    ctx.write_json(
        "transcript/disfluencies.json",
        {
            "schema_version": 1,
            "status": "ready",
            "events": [{"event_id": "x", "start_ms": 0, "end_ms": 1, "review_status": "confirmed"}],
            "stats": {},
        },
    )
    out = attach_disfluency_context({"foo": 1}, ctx)
    assert "disfluency_catalog" in out
    assert out["foo"] == 1


def test_mix_skips_overlay_on_disfluency_window(tmp_path: Path, monkeypatch) -> None:
    cfg = {
        "disfluency_extract": {"enabled": True},
        "disfluency_restore": {"enabled": True, "crossfade_ms": 20},
        "mix": {"crossfade_ms_flow1": 80, "completeness_gate": {"enabled": False}},
    }
    patch_merged_config(monkeypatch, cfg)
    ctx = isolated_run_ctx(tmp_path, "run_mix_df")

    # Minimal silent WAV for ingest + disfluency clip
    from pydub import AudioSegment

    ingest = ctx.path("ingest", "normalized.wav")
    ingest.parent.mkdir(parents=True, exist_ok=True)
    AudioSegment.silent(duration=10000, frame_rate=48000).export(str(ingest), format="wav")

    clip_path = ctx.path("transcript", "disfluency_clips", "fill_0001.wav")
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    AudioSegment.silent(duration=300, frame_rate=48000).export(str(clip_path), format="wav")

    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_a"],
            "timeline_duration_ms": 10300,
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_a",
                    "source_start_ms": 0,
                    "source_end_ms": 5000,
                    "timeline_start_ms": 0,
                    "duration_ms": 5000,
                },
                {
                    "type": "disfluency",
                    "event_id": "fill_0001",
                    "segment_id": "seg_a",
                    "source_path": "transcript/disfluency_clips/fill_0001.wav",
                    "timeline_start_ms": 5000,
                    "duration_ms": 300,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_a",
                    "source_start_ms": 5000,
                    "source_end_ms": 10000,
                    "timeline_start_ms": 5300,
                    "duration_ms": 4700,
                },
            ],
        },
    )
    ctx.write_json("transcript/full.json", {"words": []}, skip_handoff=True)

    overlay_calls: list[int] = []

    def fake_overlays(*_a, **_k):
        from pydub import AudioSegment as AS

        sting = AS.silent(duration=500, frame_rate=48000)
        return [{"audio": sting, "position_ms": 5100, "role": "stinger"}], {"beds": 0, "stingers": 1, "bridges": 0, "missing_assets": 0}

    real_overlay = __import__("pydub").AudioSegment.overlay

    def counting_overlay(self, other, position=0):
        overlay_calls.append(position)
        return real_overlay(self, other, position=position)

    with patch("interview_mux.sound_design.load_profile", return_value={"pacing": {"pace_class": "measured"}}):
        with patch("interview_mux.sound_design.load_sound_design_plan", return_value=None):
            with patch("interview_mux.sound_design.enforce_mix_completeness"):
                with patch("interview_mux.sound_design.maybe_check_mix_intelligibility"):
                    with patch("interview_mux.sound_design.build_flow1_overlays", side_effect=fake_overlays):
                        with patch("pydub.audio_segment.AudioSegment.overlay", counting_overlay):
                            mix(ctx)

    assert 5100 not in overlay_calls, f"SFX overlay at disfluency window should be skipped, got positions {overlay_calls}"
