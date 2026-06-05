from __future__ import annotations

from pydub import AudioSegment

from interview_mux.audio_timeline import (
    adaptive_crossfade_ms,
    snap_cut_to_word_boundary,
)


def test_snap_cut_to_word_boundary_nudges_toward_word_end():
    words = [{"text": "hello", "start_ms": 1000, "end_ms": 1500}]
    snapped = snap_cut_to_word_boundary(1520, words, margin_ms=20, max_shift_ms=100)
    assert snapped == 1520  # 1500 + 20 margin


def test_adaptive_crossfade_ms_within_bounds():
    tail = AudioSegment.silent(duration=200, frame_rate=48000) - 6
    head = AudioSegment.silent(duration=200, frame_rate=48000) - 6
    ms = adaptive_crossfade_ms(tail, head, min_ms=80, max_ms=200, default_ms=100)
    assert 80 <= ms <= 200
