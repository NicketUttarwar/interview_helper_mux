"""Organic / tapered music fades stay present longer then soft-land into silence."""

from __future__ import annotations

from pydub.generators import Sine

from interview_mux.audio_timeline import organic_fade_in, organic_fade_out
from interview_mux.sound_design import _bed_fade_ms


def _tone(ms: int = 4000):
    return Sine(220).to_audio_segment(duration=ms).set_channels(1).set_frame_rate(48000)


def test_organic_fade_out_is_longer_and_tapered():
    bed = _tone(3000)
    faded = organic_fade_out(bed, 1500, curve=1.8)
    assert len(faded) == len(bed)
    # Early fade region stays relatively present vs late region (tapered soft landing).
    early = faded[1500 + 100 : 1500 + 200]
    late = faded[1500 + 1200 : 1500 + 1300]
    assert early.rms > late.rms * 3
    # Tip is near silence vs unducked body.
    tip = faded[-40:]
    body = faded[500:600]
    assert tip.rms < body.rms * 0.05
    # Higher curve keeps more energy early than linear-in-dB (curve=1).
    soft = organic_fade_out(bed, 1500, curve=2.2)
    linear_db = organic_fade_out(bed, 1500, curve=1.0)
    assert soft[1500 + 200 : 1500 + 300].rms > linear_db[1500 + 200 : 1500 + 300].rms


def test_organic_fade_in_starts_quiet():
    bed = _tone(2000)
    faded = organic_fade_in(bed, 800, curve=1.6)
    assert faded[:40].rms < bed[:40].rms * 0.15
    assert faded[1200:1300].rms > faded[:40].rms


def test_bed_fade_defaults_are_long_and_resist_short_crossfade():
    fade_in, fade_out, curve = _bed_fade_ms(
        placement="under_segment",
        cue={"crossfade_ms": 120},
        profile={"placement_hints": {"bed_fade_in_ms": 700, "bed_fade_out_ms": 2200}},
    )
    assert fade_in >= 700
    assert fade_out >= 2200
    assert curve >= 1.5
    span_in, span_out, _ = _bed_fade_ms(
        placement="under_segment_span",
        cue={},
        profile=None,
    )
    assert span_out >= span_in
    assert span_out >= 3000
