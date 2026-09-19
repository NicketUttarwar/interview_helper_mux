from __future__ import annotations

from pydub import AudioSegment

from interview_mux.audio_timeline import (
    adaptive_crossfade_ms,
    snap_cut_to_word_boundary,
)
from interview_mux.sound_design import _clamp_speech_slice_to_intentional


def test_snap_cut_to_word_boundary_nudges_toward_word_end():
    words = [{"text": "hello", "start_ms": 1000, "end_ms": 1500}]
    snapped = snap_cut_to_word_boundary(1520, words, margin_ms=20, max_shift_ms=100)
    assert snapped == 1520  # 1500 + 20 margin (no following word)


def test_snap_cut_to_word_boundary_uses_pause_midpoint():
    words = [
        {"text": "hello", "start_ms": 1000, "end_ms": 1500},
        {"text": "next", "start_ms": 2500, "end_ms": 2700},
    ]
    snapped = snap_cut_to_word_boundary(1520, words, margin_ms=20, max_shift_ms=100)
    assert snapped == (1500 + 2500) // 2


def test_clamp_speech_slice_blocks_end_expansion_past_edl_cut():
    # Junction cut at 97920; word snap would expand to 97970 ("Well," reopen).
    start, end = _clamp_speech_slice_to_intentional(87320, 97920, 87320, 97970)
    assert start == 87320
    assert end == 97920


def test_clamp_speech_slice_allows_shrink_and_tiny_tol():
    start, end = _clamp_speech_slice_to_intentional(1000, 2000, 1000, 1980)
    assert end == 1980
    start2, end2 = _clamp_speech_slice_to_intentional(1000, 2000, 1000, 2015)
    assert end2 == 2015  # within 20ms expand tol


def test_adaptive_crossfade_ms_within_bounds():
    tail = AudioSegment.silent(duration=200, frame_rate=48000) - 6
    head = AudioSegment.silent(duration=200, frame_rate=48000) - 6
    ms = adaptive_crossfade_ms(tail, head, min_ms=80, max_ms=200, default_ms=100)
    assert 80 <= ms <= 200
