"""TBIY spatial mix helpers — stereo pan simulation and profile dB tiers."""

from __future__ import annotations

from typing import Any

from pydub import AudioSegment

from interview_mux.production_profile import is_tbiy, mix_rules


def apply_pan_position(audio: AudioSegment, pan_position: float | int | None) -> AudioSegment:
    """Simulate L/R pan on stereo or mono clip. pan_position: -100 (L) .. 100 (R)."""
    if pan_position is None:
        return audio
    pan = max(-100.0, min(100.0, float(pan_position)))
    if abs(pan) < 1.0:
        return audio
    if audio.channels == 1:
        audio = audio.set_channels(2)
    left_gain = 1.0 - max(0.0, pan / 100.0) * 0.35
    right_gain = 1.0 + min(0.0, pan / 100.0) * 0.35
    if pan > 0:
        left_gain = 1.0 - (pan / 100.0) * 0.35
        right_gain = 1.0
    else:
        left_gain = 1.0
        right_gain = 1.0 + (pan / 100.0) * 0.35
    left, right = audio.split_to_mono()
    left = left.apply_gain(20 * (left_gain - 1.0))
    right = right.apply_gain(20 * (right_gain - 1.0))
    return AudioSegment.from_mono_audiosegments(left, right)


def tbiy_level_adjustment_db(ctx: Any, cue: dict[str, Any], asset: dict[str, Any]) -> float:
    """Optional level_db tweak from production profile when tbiy."""
    if not is_tbiy(ctx):
        return 0.0
    rules = mix_rules(ctx)
    role = str(asset.get("role") or "")
    if role == "rhetorical_punctuator":
        peak = float(rules.get("punctuator_peak_db", -10))
        return peak - float(cue.get("level_db", -24))
    if role in ("era_music_bed", "ambient_bed"):
        return float(rules.get("bed_under_dialogue_db", -26)) - float(cue.get("level_db", -24))
    if role == "environmental_foley":
        return float(rules.get("foley_under_dialogue_db", -26)) - float(cue.get("level_db", -24))
    return 0.0


def tbiy_duck_db(ctx: Any, cue: dict[str, Any], default: float) -> float:
    if not is_tbiy(ctx):
        return default
    rules = mix_rules(ctx)
    return max(6.0, float(cue.get("duck_under_speech_db", rules.get("bed_duck_db", default))))
