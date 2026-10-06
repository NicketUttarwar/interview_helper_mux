"""Chapter music-bridge grammar: eligibility, EDL air, junction exemption, coverage band."""

from __future__ import annotations

import pytest

from interview_mux.air_script import cues_from_sonic_plan, hunt_sonic_opportunities
from interview_mux.assembly_ledger import HITCH_AIR_KINDS
from interview_mux.chapter_music_bridge import (
    CHAPTER_MUSIC_BRIDGE_AIR_KIND,
    apply_bridge_sparsity,
    bridge_duration_ms,
    chapter_hinge_earns_bridge,
    is_light_transition_line,
    is_substantial_vo_line,
    vo_line_earns_bridge,
)
from interview_mux.junction_snip_qa import detect_junction_findings
from interview_mux.listenability_guards import listenability_guards_cfg
from interview_mux.mastering_plan_loader import write_plan
from interview_mux.order_hash import stamp_order_hash
from interview_mux.stages.assembly import build_flow1_edl
from run_fixtures import isolated_run_ctx


def test_bridge_duration_default_4s() -> None:
    assert bridge_duration_ms() == 4000


def test_bed_coverage_max_is_099() -> None:
    cfg = listenability_guards_cfg()
    assert cfg["bed_coverage_min_ratio"] == pytest.approx(0.40)
    assert cfg["bed_coverage_max_ratio"] == pytest.approx(0.99)


def test_light_transition_excluded() -> None:
    assert is_light_transition_line(
        {"cue_role": "vo_bridge", "text": "And then…", "transition_type": "bridge"}
    )
    assert is_light_transition_line(
        {"line_category": "story_bridge", "text": "Meanwhile"}
    )
    assert not is_light_transition_line(
        {
            "transition_type": "chapter",
            "text": " ".join(["word"] * 24),
            "detail_budget": "dense",
        }
    )


def test_substantial_vo_requires_length() -> None:
    short = {
        "cue_role": "vo_bridge",
        "text": "Quick bridge",
        "estimated_duration_sec": 1.5,
    }
    assert not is_substantial_vo_line(short)
    assert not vo_line_earns_bridge(short, montage_move="vo_then_clip")

    dense = {
        "detail_budget": "dense",
        "information_package_id": "pkg_1",
        "text": " ".join(["insight"] * 22),
        "estimated_duration_sec": 8.0,
    }
    assert is_substantial_vo_line(dense)
    assert vo_line_earns_bridge(dense, montage_move="information_package")


def test_chapter_hinge_eligibility() -> None:
    assert chapter_hinge_earns_bridge(transition_type="chapter")
    assert chapter_hinge_earns_bridge(is_chapter_scale=True)
    assert chapter_hinge_earns_bridge(scene_resolve=True)
    assert not chapter_hinge_earns_bridge(transition_type="bridge")
    assert not chapter_hinge_earns_bridge(transition_type="chapter", same_answer=True)


def test_sparsity_one_per_after_and_min_separation() -> None:
    ordered = [f"seg_{i:03d}" for i in range(1, 12)]
    opps = [
        {"kind": "scene_bed", "segment_id": "seg_001"},
        {
            "kind": "chapter_music_bridge",
            "segment_id": "seg_001",
            "after_segment_id": "seg_001",
        },
        {
            "kind": "chapter_music_bridge",
            "segment_id": "seg_001",
            "after_segment_id": "seg_001",
        },
        {
            "kind": "chapter_music_bridge",
            "segment_id": "seg_002",
            "after_segment_id": "seg_002",
        },
        {
            "kind": "chapter_music_bridge",
            "segment_id": "seg_010",
            "after_segment_id": "seg_010",
        },
    ]
    durs = {sid: 20_000 for sid in ordered}
    out = apply_bridge_sparsity(opps, segment_durs=durs, ordered_segment_ids=ordered)
    bridges = [o for o in out if o.get("kind") == "chapter_music_bridge"]
    afters = [o.get("after_segment_id") for o in bridges]
    assert afters.count("seg_001") == 1
    # seg_002 is only 20s after seg_001 end → filtered by min separation
    assert "seg_002" not in afters
    # seg_010 is ~180s later → kept
    assert "seg_010" in afters


def test_hitch_air_kinds_include_bridge() -> None:
    assert CHAPTER_MUSIC_BRIDGE_AIR_KIND in HITCH_AIR_KINDS


def test_hunt_emits_bridge_between_scenes(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_cmb_hunt")
    ordered = ["seg_001", "seg_002", "seg_010", "seg_011"]
    segs = []
    t = 0
    for i, sid in enumerate(ordered):
        segs.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_0",
                "speaker_role": "interviewee",
                "type": "interviewee_answer",
                "start_ms": t,
                "end_ms": t + 10_000,
                "text": f"Beat {i}",
                "topic_tags": ["origin_story"],
            }
        )
        t += 12_000
    ctx.write_json("segments/manifest.json", {"segments": segs})
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ordered})
    write_plan(
        ctx,
        {
            "version": 1,
            "story_spine": {
                "scenes": [
                    {"scene_id": "sc_a", "segment_ids": ["seg_001", "seg_002"]},
                    {"scene_id": "sc_b", "segment_ids": ["seg_010", "seg_011"]},
                ]
            },
            "air_script": {
                "beats": [
                    {"segment_id": "seg_010", "montage_move": "information_package"},
                ]
            },
            "circumstance_card": {},
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_pkg",
                    "targets_segment_id": "seg_010",
                    "placement": "before",
                    "detail_budget": "dense",
                    "text": " ".join(["context"] * 24),
                    "estimated_duration_sec": 9.0,
                }
            ]
        },
    )
    opps = hunt_sonic_opportunities(ctx)
    kinds = [o.get("kind") for o in opps]
    assert "chapter_music_bridge" in kinds
    bridges = [o for o in opps if o.get("kind") == "chapter_music_bridge"]
    assert all(int(o.get("duration_ms") or 0) == 4000 for o in bridges)
    assets_by_kind = {
        "stinger": [
            {
                "asset_id": "show_theme_v1_stinger_01",
                "role": "theme_transition",
                "palette_kind": "stingers",
            }
        ],
        "theme_transition": [
            {
                "asset_id": "show_theme_v1_stinger_01",
                "role": "theme_transition",
                "palette_kind": "stingers",
            }
        ],
    }
    plan = {"sonic_opportunities": opps}
    cues = cues_from_sonic_plan(plan, assets_by_kind=assets_by_kind)
    bridge_cues = [c for c in cues if c.get("chapter_music_bridge")]
    assert bridge_cues
    assert all(c.get("preserve_bridge_ms") == 4000 for c in bridge_cues)
    assert all(c.get("carry_into_next") for c in bridge_cues)


def test_edl_reserves_chapter_music_bridge_on_chapter_transition(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_cmb_edl")
    segs = {
        "seg_001": {
            "segment_id": "seg_001",
            "speaker_id": "spk_0",
            "start_ms": 0,
            "end_ms": 8_000,
            "text": "First chapter close.",
        },
        "seg_010": {
            "segment_id": "seg_010",
            "speaker_id": "spk_1",
            "start_ms": 120_000,
            "end_ms": 128_000,
            "text": "Second chapter open.",
        },
    }
    selection = {"ordered_segment_ids": ["seg_001", "seg_010"]}
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_010",
                "type": "chapter",
                "text": " ".join(["Now"] * 20),
            }
        ]
    }
    edl = build_flow1_edl(
        selection=selection,
        segments_by_id=segs,
        gap_report={"interviewer_lines": []},
        transitions=transitions,
        ctx=ctx,
    )
    air = [
        c
        for c in edl["clips"]
        if c.get("type") == "silence"
        and c.get("air_kind") == CHAPTER_MUSIC_BRIDGE_AIR_KIND
    ]
    assert air
    assert air[0]["duration_ms"] == 4000
    bridge_i = next(
        i
        for i, c in enumerate(edl["clips"])
        if c.get("air_kind") == CHAPTER_MUSIC_BRIDGE_AIR_KIND
    )
    tr_i = next(i for i, c in enumerate(edl["clips"]) if c.get("type") == "transition")
    assert bridge_i < tr_i


def test_short_vo_bridge_does_not_reserve_music_bridge(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_cmb_short_vo")
    segs = {
        "seg_001": {
            "segment_id": "seg_001",
            "speaker_id": "spk_0",
            "start_ms": 0,
            "end_ms": 5_000,
            "text": "Hello.",
        },
        "seg_002": {
            "segment_id": "seg_002",
            "speaker_id": "spk_1",
            "start_ms": 5_500,
            "end_ms": 12_000,
            "text": "Answer continues.",
        },
    }
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_short",
                "targets_segment_id": "seg_002",
                "placement": "before",
                "delivery": "record",
                "cue_role": "vo_bridge",
                "line_category": "story_bridge",
                "transition_type": "bridge",
                "text": "And then",
                "estimated_duration_sec": 1.0,
            }
        ]
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_001", "seg_002"]},
        segments_by_id=segs,
        gap_report=gap,
        transitions={"transitions": []},
        ctx=ctx,
    )
    assert not any(
        c.get("air_kind") == CHAPTER_MUSIC_BRIDGE_AIR_KIND for c in edl["clips"]
    )


def test_chapter_music_bridge_not_dead_air_stack(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_cmb_junction")
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_002",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "start_ms": 60000,
                    "end_ms": 70000,
                    "text": "Second chapter open.",
                    "topic_tags": ["origin_story"],
                }
            ]
        },
    )
    clips = [
        {
            "type": "silence",
            "air_kind": "chapter_music_bridge",
            "timeline_start_ms": 0,
            "duration_ms": 4000,
            "preserve_planned_music": True,
        },
        {
            "type": "speech",
            "segment_id": "seg_002",
            "source_start_ms": 60000,
            "source_end_ms": 70000,
            "timeline_start_ms": 4000,
            "duration_ms": 10000,
        },
    ]
    edl = stamp_order_hash(
        {
            "version": 1,
            "ordered_segment_ids": ["seg_002"],
            "clips": clips,
            "timeline_duration_ms": 14000,
        }
    )
    findings = detect_junction_findings(ctx, edl)
    assert not any(f.get("kind") == "dead_air_stack" for f in findings)


def test_enhance_speech_free_theme_accepts_stereo_and_is_idempotent() -> None:
    """Regression: chapter-bridge path used to re-enhance an already-stereo cue."""
    from pydub import AudioSegment

    from interview_mux.sound_design import DEFAULT_FRAME_RATE, enhance_speech_free_theme

    mono = AudioSegment.silent(duration=500, frame_rate=DEFAULT_FRAME_RATE).set_channels(1)
    # Inject non-silence so high-pass / overlay have content.
    mono = mono.overlay(
        AudioSegment.silent(duration=500, frame_rate=DEFAULT_FRAME_RATE)
        .set_channels(1)
        .apply_gain(6.0)
    )
    once = enhance_speech_free_theme(mono, role="theme_emphasis")
    assert once.channels == 2
    twice = enhance_speech_free_theme(once, role="theme_emphasis")
    assert twice.channels == 2
    # Stereo input that never went through enhance also collapses safely.
    stereo_in = AudioSegment.from_mono_audiosegments(mono, mono)
    assert enhance_speech_free_theme(stereo_in, role="theme_chapter_resolve").channels == 2


def test_chapter_bridge_pad_matches_cue_channels() -> None:
    """Pad silence must share channel count with an already-widened bridge cue."""
    from pydub import AudioSegment

    from interview_mux.sound_design import DEFAULT_FRAME_RATE, enhance_speech_free_theme

    base = AudioSegment.silent(duration=800, frame_rate=DEFAULT_FRAME_RATE).set_channels(1)
    cue_audio = enhance_speech_free_theme(base, role="theme_transition")
    assert cue_audio.channels == 2
    bridge_ms = 4000
    pad = AudioSegment.silent(
        duration=bridge_ms - len(cue_audio),
        frame_rate=cue_audio.frame_rate or DEFAULT_FRAME_RATE,
    )
    if cue_audio.channels and pad.channels != cue_audio.channels:
        pad = pad.set_channels(int(cue_audio.channels))
    out = (cue_audio + pad)[:bridge_ms]
    assert len(out) == bridge_ms
    assert out.channels == cue_audio.channels


def test_flow1_chapter_bridge_does_not_reenhance() -> None:
    import inspect

    from interview_mux import sound_design

    src = inspect.getsource(sound_design.flow1_overlays_from_sdp)
    # Presence runs once on base for accent roles; bridge body must not re-call.
    assert "cue_audio = enhance_speech_free_theme(cue_audio, role=asset_role)" not in src
    assert "base = enhance_speech_free_theme(base, role=asset_role)" in src
