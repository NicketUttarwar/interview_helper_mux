from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment
from pydub.generators import Sine

from interview_mux.run_context import RunContext
from interview_mux.sound_design import (
    _laughter_windows_from_value_features,
    _nudge_away_from_laughter,
    flow1_overlays_from_sdp,
    resolve_stinger_position_ms,
)
from run_fixtures import minimal_manifest, minimal_manifest_segment, minimal_source_acoustic_profile, sound_design_plan_with


def _profile(*, prefer: bool = True, min_pause: int = 400) -> dict:
    return minimal_source_acoustic_profile(
        placement_hints={
            "prefer_stinger_after_pause_tail": prefer,
            "stinger_min_pause_after_speech_ms": min_pause,
        }
    )


def _segment(seg_id: str, start_ms: int, end_ms: int) -> dict:
    return {"segment_id": seg_id, "start_ms": start_ms, "end_ms": end_ms}


def test_resolve_stinger_finds_gap_before_segment_start() -> None:
    transcript = {
        "words": [
            {"text": "one", "start_ms": 0, "end_ms": 200},
            {"text": "two", "start_ms": 700, "end_ms": 900},
            {"text": "three", "start_ms": 1000, "end_ms": 1200},
        ]
    }
    segment = _segment("seg_b", start_ms=1000, end_ms=3000)
    pos = resolve_stinger_position_ms(segment, transcript, _profile(), placement="before_segment")
    assert pos == 900


def test_resolve_stinger_finds_trailing_pause_after_segment() -> None:
    transcript = {
        "words": [
            {"text": "alpha", "start_ms": 1000, "end_ms": 1300},
            {"text": "beta", "start_ms": 1400, "end_ms": 1700},
        ]
    }
    segment = _segment("seg_a", start_ms=1000, end_ms=2500)
    pos = resolve_stinger_position_ms(segment, transcript, _profile(), placement="after_segment")
    assert pos == 1700


def test_resolve_stinger_returns_none_when_gap_too_short() -> None:
    transcript = {
        "words": [
            {"text": "fast", "start_ms": 0, "end_ms": 200},
            {"text": "talk", "start_ms": 250, "end_ms": 450},
        ]
    }
    segment = _segment("seg_a", start_ms=0, end_ms=2000)
    pos = resolve_stinger_position_ms(segment, transcript, _profile(min_pause=400), placement="before_segment")
    assert pos is None


def test_resolve_stinger_respects_prefer_flag() -> None:
    transcript = {
        "words": [
            {"text": "one", "start_ms": 0, "end_ms": 200},
            {"text": "two", "start_ms": 700, "end_ms": 900},
        ]
    }
    segment = _segment("seg_a", start_ms=700, end_ms=2000)
    pos = resolve_stinger_position_ms(segment, transcript, _profile(prefer=False), placement="before_segment")
    assert pos is None


def test_laughter_windows_extracted_from_value_features() -> None:
    vf = {
        "profiles": {
            "transcript": {
                "quality_trajectory_flags": [
                    {"label": "laughter_burst", "start_ms": 850, "end_ms": 1100},
                ]
            }
        }
    }
    windows = _laughter_windows_from_value_features(vf)
    assert windows == [(850, 1100)]


def test_resolve_stinger_nudges_away_from_laughter_window() -> None:
    transcript = {
        "words": [
            {"text": "one", "start_ms": 0, "end_ms": 200},
            {"text": "two", "start_ms": 700, "end_ms": 900},
            {"text": "three", "start_ms": 1000, "end_ms": 1200},
        ]
    }
    segment = _segment("seg_b", start_ms=1000, end_ms=3000)
    laughter = [(880, 920)]
    pos = resolve_stinger_position_ms(
        segment,
        transcript,
        _profile(),
        placement="before_segment",
        laughter_windows=laughter,
    )
    assert pos == 1300


def test_nudge_away_from_laughter_returns_none_when_blocked() -> None:
    windows = [(0, 5000)]
    assert _nudge_away_from_laughter(1000, windows, buffer_ms=200) is None


def test_nudge_away_from_laughter_empty_windows_returns_original() -> None:
    assert _nudge_away_from_laughter(1000, [], buffer_ms=200) == 1000
    assert _nudge_away_from_laughter(None, [], buffer_ms=200) is None


def test_laughter_windows_missing_value_features_returns_empty() -> None:
    assert _laughter_windows_from_value_features(None) == []
    assert _laughter_windows_from_value_features({}) == []


def test_flow1_overlays_uses_pause_tail_not_segment_start(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_stinger_pause", create=True)

    tone = Sine(440).to_audio_segment(duration=3000).set_channels(1).set_frame_rate(48000)
    sting = Sine(880).to_audio_segment(duration=400).set_channels(1).set_frame_rate(48000)
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    ctx.path("sound_design", "assets").mkdir(parents=True, exist_ok=True)
    tone.export(str(ctx.path("ingest", "normalized.wav")), format="wav")
    sting.export(str(ctx.path("sound_design", "assets", "chapter_stinger_warm.wav")), format="wav")

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a", start_ms=800, end_ms=3000),
        ),
    )
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "outro", "start_ms": 100, "end_ms": 300},
                {"text": "chapter", "start_ms": 800, "end_ms": 1000},
            ]
        },
    )
    ctx.write_json(
        "understanding/source_acoustic_profile.json",
        _profile(min_pause=400),
    )
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "chapter_stinger_warm",
                    "role": "chapter_stinger",
                    "description": "warm chapter stinger",
                    "duration_seconds": 0.4,
                }
            ],
            flow_plans={
                "podcast": {
                    "cues": [
                        {
                            "cue_id": "sting_1",
                            "asset_id": "chapter_stinger_warm",
                            "placement": "before_segment",
                            "segment_id": "seg_a",
                            "level_db": -12.0,
                        }
                    ],
                }
            },
            generated={"chapter_stinger_warm": "sound_design/assets/chapter_stinger_warm.wav"},
        ),
    )

    segment_timing = {"seg_a": (1000, 3200)}
    overlays = flow1_overlays_from_sdp(ctx, segment_timing=segment_timing)
    assert len(overlays) == 1
    # outro ends 300; segment source starts 800 → timeline 1000 + (300 - 800) = 500
    assert overlays[0]["position_ms"] == 500


def test_flow1_overlays_pause_trigger_rhetorical_punctuator(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_punctuator_pause", create=True)

    tone = Sine(440).to_audio_segment(duration=3000).set_channels(1).set_frame_rate(48000)
    sting = Sine(880).to_audio_segment(duration=400).set_channels(1).set_frame_rate(48000)
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    ctx.path("sound_design", "assets").mkdir(parents=True, exist_ok=True)
    tone.export(str(ctx.path("ingest", "normalized.wav")), format="wav")
    sting.export(str(ctx.path("sound_design", "assets", "punctuator_ding.wav")), format="wav")

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_a", start_ms=800, end_ms=3000),
        ),
    )
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "outro", "start_ms": 100, "end_ms": 300},
                {"text": "chapter", "start_ms": 800, "end_ms": 1000},
            ]
        },
    )
    ctx.write_json("understanding/source_acoustic_profile.json", _profile(min_pause=400))
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "punctuator_ding",
                    "role": "rhetorical_punctuator",
                    "description": "dry ding",
                    "duration_seconds": 0.35,
                }
            ],
            flow_plans={
                "podcast": {
                    "cues": [
                        {
                            "cue_id": "punc_1",
                            "asset_id": "punctuator_ding",
                            "placement": "before_segment",
                            "segment_id": "seg_a",
                            "trigger": "pause",
                            "level_db": -14.0,
                            "pan_position": -60,
                        }
                    ],
                }
            },
            generated={"punctuator_ding": "sound_design/assets/punctuator_ding.wav"},
        ),
    )

    overlays = flow1_overlays_from_sdp(ctx, segment_timing={"seg_a": (1000, 3200)})
    assert len(overlays) == 1
    assert overlays[0]["position_ms"] == 500
    assert overlays[0]["role"] == "punctuator"
