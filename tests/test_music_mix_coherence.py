"""Tests for music open grammar, cue binding, and lane exclusivity."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment
from pydub.generators import Sine

from interview_mux.music_lane import (
    apply_music_lane_exclusivity,
    bind_cues_to_theme_assets,
    cold_open_position_ms,
    collapse_duplicate_music_cues,
    effective_cue_role,
    validate_music_cue_coherence,
    vo_open_landmarks_from_edl,
)
from interview_mux.sound_design import flow1_cue_position, flow1_overlays_from_sdp
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment, sound_design_plan_with


def _theme_assets() -> list[dict]:
    return [
        {
            "asset_id": "show_theme_v1_cold_open",
            "role": "theme_cold_open",
            "description": "cold open theme",
            "duration_seconds": 8,
        },
        {
            "asset_id": "show_theme_v1_underscore",
            "role": "theme_underscore",
            "description": "underscore bed",
            "duration_seconds": 8,
        },
        {
            "asset_id": "show_theme_v1_emphasis",
            "role": "theme_emphasis",
            "description": "emphasis punctuator",
            "duration_seconds": 4,
        },
        {
            "asset_id": "show_theme_v1_chapter_resolve",
            "role": "theme_chapter_resolve",
            "description": "chapter resolve",
            "duration_seconds": 4,
        },
        {
            "asset_id": "show_theme_v1_outro",
            "role": "theme_outro",
            "description": "outro theme",
            "duration_seconds": 8,
        },
    ]


def test_effective_role_falls_back_to_asset():
    cue = {"cue_id": "cold_open", "asset_id": "show_theme_v1_cold_open", "placement": "before_segment"}
    asset = {"asset_id": "show_theme_v1_cold_open", "role": "theme_cold_open"}
    assert effective_cue_role(cue, asset) == "theme_cold_open"


def test_cold_open_position_between_preface_and_question():
    landmarks = {
        "preface_end_ms": 28000,
        "first_question_start_ms": 45000,
        "first_speech_start_ms": 52000,
    }
    pos = cold_open_position_ms(
        theme_duration_ms=8000,
        landmarks=landmarks,
        segment_timing={"seg_001": (52000, 90000)},
        air_ms=400,
    )
    assert 28000 <= pos < 45000
    assert pos + 8000 <= 45000


def test_flow1_cue_position_uses_asset_role_and_landmarks():
    cue = {
        "cue_id": "cold_open",
        "asset_id": "show_theme_v1_cold_open",
        "placement": "before_segment",
        "segment_id": "seg_001",
    }
    landmarks = {
        "preface_end_ms": 10000,
        "first_question_start_ms": 20000,
        "first_speech_start_ms": 30000,
    }
    pos = flow1_cue_position(
        cue=cue,
        segment_timing={"seg_001": (30000, 60000)},
        role="theme_cold_open",
        vo_landmarks=landmarks,
        theme_duration_ms=5000,
    )
    assert pos is not None
    assert 10000 <= pos < 20000


def test_bind_cues_to_matching_theme_assets():
    cues = [
        {
            "cue_id": "cold_open",
            "asset_id": "show_theme_v1_cold_open",
            "placement": "before_segment",
            "segment_id": "seg_001",
        },
        {
            "cue_id": "emphasis_growth",
            "asset_id": "show_theme_v1_cold_open",
            "placement": "before_segment",
            "segment_id": "seg_001",
        },
        {
            "cue_id": "resolve_ch1",
            "asset_id": "show_theme_v1_cold_open",
            "placement": "after_segment",
            "after_segment_id": "seg_005",
        },
        {
            "cue_id": "outro_final",
            "asset_id": "show_theme_v1_cold_open",
            "placement": "after_segment",
            "after_segment_id": "seg_172",
        },
    ]
    bound, applied = bind_cues_to_theme_assets(cues, _theme_assets())
    by_id = {c["cue_id"]: c for c in bound}
    assert by_id["emphasis_growth"]["asset_id"] == "show_theme_v1_emphasis"
    assert by_id["resolve_ch1"]["asset_id"] == "show_theme_v1_chapter_resolve"
    assert by_id["outro_final"]["asset_id"] == "show_theme_v1_outro"
    assert any(a.get("action") == "bind_cue_theme_asset" for a in applied)


def test_collapse_duplicate_before_segment_cues():
    assets = {a["asset_id"]: a for a in _theme_assets()}
    cues = [
        {
            "cue_id": "cold_open",
            "asset_id": "show_theme_v1_cold_open",
            "role": "theme_cold_open",
            "placement": "before_segment",
            "segment_id": "seg_001",
        },
        {
            "cue_id": "cold_open_dup",
            "asset_id": "show_theme_v1_cold_open",
            "role": "theme_cold_open",
            "placement": "before_segment",
            "segment_id": "seg_001",
        },
        {
            "cue_id": "emphasis_growth",
            "asset_id": "show_theme_v1_emphasis",
            "role": "theme_emphasis",
            "placement": "before_segment",
            "segment_id": "seg_001",
        },
    ]
    out, applied = collapse_duplicate_music_cues(cues, assets)
    cold = [c for c in out if str(c.get("role")) == "theme_cold_open"]
    assert len(cold) == 1
    assert any(a.get("action") == "collapse_duplicate_music_cue" for a in applied)


def test_exclusivity_drops_stacked_punctuator_over_bookend():
    bookend = {
        "audio": Sine(440).to_audio_segment(duration=2000),
        "position_ms": 1000,
        "role": "theme",
        "music_role": "theme_cold_open",
    }
    punct = {
        "audio": Sine(550).to_audio_segment(duration=1500),
        "position_ms": 1200,
        "role": "theme_punctuator",
        "music_role": "theme_emphasis",
    }
    bed = {
        "audio": Sine(220).to_audio_segment(duration=5000),
        "position_ms": 1000,
        "role": "bed",
        "music_role": "theme_underscore",
    }
    out = apply_music_lane_exclusivity([bookend, punct, bed], crossfade_ms=300)
    roles = [o.get("role") for o in out]
    assert "theme" in roles
    # Punctuator fully overlapping bookend should not survive at full dual sum.
    assert roles.count("theme_punctuator") == 0 or all(
        abs(int(o.get("position_ms") or 0) - 1200) > 50
        for o in out
        if o.get("role") == "theme_punctuator"
    )


def test_validate_rejects_multiple_cold_opens_and_role_mismatch():
    cues = [
        {
            "cue_id": "cold_open",
            "asset_id": "show_theme_v1_cold_open",
            "placement": "before_segment",
            "segment_id": "seg_001",
        },
        {
            "cue_id": "theme_cold_open_seed",
            "asset_id": "show_theme_v1_cold_open",
            "placement": "before_segment",
            "segment_id": "seg_001",
        },
        {
            "cue_id": "emphasis_x",
            "asset_id": "show_theme_v1_cold_open",
            "placement": "before_segment",
            "segment_id": "seg_002",
        },
    ]
    errs = validate_music_cue_coherence(cues, _theme_assets())
    assert any("at most one theme_cold_open" in e for e in errs)
    assert any("mismatches intent" in e for e in errs)


def test_vo_landmarks_from_edl_exec_open_shape():
    edl = {
        "clips": [
            {
                "type": "vo_pickup",
                "line_id": "vo_preface_001",
                "timeline_start_ms": 0,
                "duration_ms": 28000,
            },
            {"type": "silence", "timeline_start_ms": 28000, "duration_ms": 1800},
            {
                "type": "vo_pickup",
                "line_id": "vo_q_001",
                "timeline_start_ms": 29800,
                "duration_ms": 7000,
            },
            {
                "type": "speech",
                "segment_id": "seg_001",
                "timeline_start_ms": 38000,
                "duration_ms": 60000,
            },
        ]
    }
    marks = vo_open_landmarks_from_edl(edl)
    assert marks["preface_end_ms"] == 28000
    assert marks["first_question_start_ms"] == 29800
    assert marks["first_speech_start_ms"] == 38000


def test_flow1_overlays_open_grammar_and_collapse(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_music_open")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_001", start_ms=0, end_ms=60000),
        ),
        skip_handoff=True,
    )
    ctx.write_json("transcript/full.json", {"words": []}, skip_handoff=True)
    assets = _theme_assets()
    sfx_dir = ctx.path("sound_design", "assets")
    sfx_dir.mkdir(parents=True, exist_ok=True)
    for a in assets:
        tone = Sine(440).to_audio_segment(duration=int(float(a["duration_seconds"]) * 1000))
        tone.export(str(sfx_dir / f"{a['asset_id']}.wav"), format="wav")
    plan = sound_design_plan_with(
        assets=assets,
        flow_plans={
            "podcast": {
                "profile": "podcast",
                "cues": [
                    {
                        "cue_id": "cold_open",
                        "asset_id": "show_theme_v1_cold_open",
                        "placement": "before_segment",
                        "segment_id": "seg_001",
                    },
                    {
                        "cue_id": "emphasis_growth",
                        "asset_id": "show_theme_v1_cold_open",
                        "placement": "before_segment",
                        "segment_id": "seg_001",
                    },
                    {
                        "cue_id": "emphasis_employee_pool",
                        "asset_id": "show_theme_v1_cold_open",
                        "placement": "before_segment",
                        "segment_id": "seg_001",
                    },
                    {
                        "cue_id": "bed_seg_001",
                        "asset_id": "show_theme_v1_underscore",
                        "placement": "under_segment",
                        "segment_id": "seg_001",
                        "level_db": -28,
                    },
                ],
            }
        },
    )
    ctx.write_json("understanding/sound_design_plan.json", plan, skip_handoff=True)
    landmarks = {
        "preface_end_ms": 10000,
        "first_question_start_ms": 22000,
        "first_speech_start_ms": 30000,
        "vo_windows": [(0, 10000), (22000, 28000)],
    }
    overlays = flow1_overlays_from_sdp(
        ctx,
        segment_timing={"seg_001": (30000, 90000)},
        vo_landmarks=landmarks,
        excluded_windows=list(landmarks["vo_windows"]),
    )
    themes = [o for o in overlays if o.get("role") == "theme"]
    assert len(themes) == 1
    pos = int(themes[0]["position_ms"])
    assert 10000 <= pos < 22000
    # No second full-level cold_open / emphasis stack at speech start.
    at_speech = [
        o
        for o in overlays
        if o.get("role") in {"theme", "theme_punctuator"} and abs(int(o.get("position_ms") or 0) - 30000) < 200
    ]
    assert len(at_speech) == 0
