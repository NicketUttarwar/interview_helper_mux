from pydub import AudioSegment
from pydub.generators import Sine

from interview_mux.audio_timeline import (
    append_with_crossfade,
    concat_clips_with_crossfade,
    junction_crossfade_ms,
)
from interview_mux.sound_design import _level_match_vo
from interview_mux.speaker_level_match import measure_level_db


def test_concat_clips_with_crossfade():
    clips = [AudioSegment.silent(duration=500), AudioSegment.silent(duration=500)]
    merged = concat_clips_with_crossfade(clips, 50)
    assert len(merged) > 500
    assert len(merged) < 1000


def test_append_integration():
    a = AudioSegment.silent(duration=1000)
    b = AudioSegment.silent(duration=1000)
    out = append_with_crossfade(a, b, 100)
    assert len(out) == len(a) + len(b) - 100


def test_junction_crossfade_table_is_type_specific():
    cfg = {
        "speech_to_vo": 155,
        "vo_to_speech": 185,
        "music_to_speech": 210,
    }
    assert junction_crossfade_ms("speech", "vo_pickup", config=cfg) == 155
    assert junction_crossfade_ms("transition", "speech", config=cfg) == 185
    assert junction_crossfade_ms("music", "speech", config=cfg) == 210


def test_vo_level_matches_both_adjacent_native_clips(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.sound_design._mix_cfg",
        lambda: {
            "vo_adjacent_level_match": {
                "enabled": True,
                "max_gain_db": 8,
                "reference_window_ms": 1000,
            }
        },
    )
    previous = Sine(220).to_audio_segment(duration=1200).apply_gain(-12)
    following = Sine(220).to_audio_segment(duration=1200).apply_gain(-16)
    vo = Sine(440).to_audio_segment(duration=800).apply_gain(-22)
    matched = _level_match_vo(
        vo,
        previous_native=previous,
        next_native=following,
    )
    prev_level = measure_level_db(previous[-1000:])
    next_level = measure_level_db(following[:1000])
    assert prev_level is not None and next_level is not None
    expected = (prev_level + next_level) / 2.0
    matched_level = measure_level_db(matched)
    assert matched_level is not None
    assert abs(matched_level - expected) < 0.35


def test_vo_level_match_handles_native_clip_shorter_than_reference_window(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.sound_design._mix_cfg",
        lambda: {
            "vo_adjacent_level_match": {
                "enabled": True,
                "max_gain_db": 8,
                "reference_window_ms": 4000,
            }
        },
    )
    native = Sine(220).to_audio_segment(duration=180).apply_gain(-14)
    vo = Sine(440).to_audio_segment(duration=500).apply_gain(-20)
    matched = _level_match_vo(vo, previous_native=native)
    native_level = measure_level_db(native)
    matched_level = measure_level_db(matched)
    assert native_level is not None and matched_level is not None
    assert abs(matched_level - native_level) < 0.35
