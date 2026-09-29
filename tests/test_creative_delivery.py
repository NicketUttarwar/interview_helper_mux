"""Tests for creative delivery policy (SFX/music + editorial shaping)."""

from __future__ import annotations

from interview_mux.creative_delivery import (
    apply_creative_mix_contract,
    hydrate_flow_cue_segments,
    validate_creative_density,
    validate_cue_segment_anchors,
)
from run_fixtures import (
    isolated_run_ctx,
    minimal_source_acoustic_profile,
    seed_analysis_ready_artifacts,
    sound_design_plan_with,
)


def test_hydrate_cue_segments_from_cue_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_hydrate_cues")
    seed_analysis_ready_artifacts(ctx)
    # seed_analysis_ready_artifacts only seeds seg_001, so seg_002 / seg_003 are
    # orphans that sanitize drops, collapsing the order to [seg_001] and making
    # every cue hydrate to the first selected segment. Seed the segments this
    # test actually orders.
    from run_fixtures import minimal_manifest

    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_001", "seg_002", "seg_003"),
        stage_key="segment_classification",
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_001", "seg_002", "seg_003"],
            "chapters": [
                {"title": "A", "segment_ids": ["seg_001", "seg_002"]},
                {"title": "B", "segment_ids": ["seg_003"]},
            ],
        },
        skip_handoff=True,
    )
    sdp = sound_design_plan_with(
        assets=[
            {"asset_id": "bed_open", "role": "ambient_bed", "duration_seconds": 8},
            {"asset_id": "sting", "role": "chapter_stinger", "duration_seconds": 2},
            {"asset_id": "accent", "role": "accent_foley", "duration_seconds": 1.5},
        ],
        flow_plans={
            "podcast": {
                "profile": "podcast",
                "cues": [
                    {"cue_id": "bed_seg_002", "asset_id": "bed_open", "placement": "under_segment"},
                    {"cue_id": "stinger_ch_01", "asset_id": "sting", "placement": "after_segment"},
                    {"cue_id": "accent_pivot_seg_003", "asset_id": "accent", "placement": "after_segment"},
                ],
            }
        },
    )
    actions = hydrate_flow_cue_segments(ctx, sdp)
    cues = sdp["flow_plans"]["podcast"]["cues"]
    by_id = {c["cue_id"]: c for c in cues}
    assert by_id["bed_seg_002"]["segment_id"] == "seg_002"
    assert by_id["stinger_ch_01"]["after_segment_id"] == "seg_002"
    assert by_id["accent_pivot_seg_003"]["after_segment_id"] == "seg_003"
    assert actions


def test_hydrate_copies_under_segment_id_and_first_selected(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_hydrate_under")
    seed_analysis_ready_artifacts(ctx)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_002"]},
        skip_handoff=True,
    )
    sdp = sound_design_plan_with(
        assets=[{"asset_id": "bed_open", "role": "ambient_bed", "duration_seconds": 8}],
        flow_plans={
            "podcast": {
                "profile": "podcast",
                "cues": [
                    {
                        "cue_id": "bed_open_act",
                        "asset_id": "bed_open",
                        "placement": "under_segment",
                        "under_segment_id": "seg_002",
                    },
                    {
                        "cue_id": "bed_fallback",
                        "asset_id": "bed_open",
                        "placement": "under_segment",
                    },
                ],
            }
        },
    )
    actions = hydrate_flow_cue_segments(ctx, sdp)
    cues = {c["cue_id"]: c for c in sdp["flow_plans"]["podcast"]["cues"]}
    assert cues["bed_open_act"]["segment_id"] == "seg_002"
    assert cues["bed_fallback"]["segment_id"] == "seg_001"
    assert actions


def test_validate_creative_density_requires_assets_and_cues(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_creative_density")
    seed_analysis_ready_artifacts(ctx)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_002"]},
        skip_handoff=True,
    )
    sparse = sound_design_plan_with(
        assets=[{"asset_id": "bed", "role": "ambient_bed", "duration_seconds": 8}],
        flow_plans={
            "podcast": {
                "profile": "podcast",
                "cues": [
                    {
                        "cue_id": "bed_1",
                        "asset_id": "bed",
                        "placement": "under_segment",
                        "segment_id": "seg_001",
                    }
                ],
            }
        },
    )
    errors = validate_creative_density(ctx, sparse)
    assert any("assets" in e for e in errors)
    assert any("theme_emphasis" in e or "theme_cold_open" in e or "stinger" in e for e in errors)


def test_validate_cue_segment_anchors(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    cues = [{"cue_id": "bed_1", "asset_id": "bed", "placement": "under_segment"}]
    errors = validate_cue_segment_anchors(cues, {"seg_001"})
    assert any("missing segment_id" in e for e in errors)


def test_apply_creative_mix_contract_upgrades_sparse():
    out = apply_creative_mix_contract(
        {"underscore_policy": "sparse", "bed_level_db_range": [-30, -26], "duck_under_speech_db": 8}
    )
    assert out["underscore_policy"] == "normal"
    # Creative path forces audible bed band (−16…−12 by default).
    assert out["bed_level_db_range"][0] >= -16
    assert out["bed_level_db_range"][1] >= -12
    assert out["duck_under_speech_db"] >= 12


def test_apply_creative_mix_contract_keeps_dry_on_source_music_risk():
    sparse = apply_creative_mix_contract(
        {"underscore_policy": "sparse", "source_music_risk": "high", "duck_under_speech_db": 8}
    )
    assert sparse["underscore_policy"] == "sparse"
    skip = apply_creative_mix_contract(
        {"underscore_policy": "skip", "dry_beds": True, "duck_under_speech_db": 8}
    )
    assert skip["underscore_policy"] == "skip"


def test_audibility_level_db_role_aware():
    from interview_mux.creative_delivery import audibility_level_db

    bed = audibility_level_db(role="bed", default=-30.0)
    assert -16.0 <= bed <= -12.0
    cold = audibility_level_db(role="theme_cold_open", default=-20.0)
    assert cold >= -9.0
    emph = audibility_level_db(role="theme_emphasis", default=-20.0)
    assert emph >= -15.0


def test_alternate_contiguous_loop_assets_breaks_long_runs():
    from interview_mux.creative_delivery import alternate_contiguous_loop_assets

    ordered = [f"seg_{i:03d}" for i in range(1, 13)]
    cues = [
        {
            "cue_id": f"bed_{sid}",
            "placement": "under_segment",
            "segment_id": sid,
            "asset_id": "loop_a",
        }
        for sid in ordered
    ]
    changed = alternate_contiguous_loop_assets(
        cues,
        ordered=ordered,
        primary_id="loop_a",
        optional_id="loop_b",
        max_run=4,
    )
    assert changed > 0
    by_seg = {c["segment_id"]: c["asset_id"] for c in cues}
    # Four-clip scenes: A A A A B B B B A A A A
    assert {by_seg[s] for s in ordered[:4]} == {"loop_a"}
    assert {by_seg[s] for s in ordered[4:8]} == {"loop_b"}
    assert {by_seg[s] for s in ordered[8:12]} == {"loop_a"}


def test_clamp_bed_level_db_moves_placeholder_into_audible_band():
    from interview_mux.creative_delivery import audible_bed_level_db, clamp_bed_level_db

    assert -16.0 <= clamp_bed_level_db(-26.0) <= -12.0
    assert -16.0 <= audible_bed_level_db() <= -12.0


def test_adaptive_bed_level_stays_inside_audible_band(tmp_path, monkeypatch):
    """Talk-heavy tape must not bury undersores below the configured bed band."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_adaptive_bed")
    ctx.write_json(
        "understanding/source_acoustic_profile.json",
        minimal_source_acoustic_profile(pacing={"speech_active_ratio": 0.9}),
        skip_handoff=True,
    )
    from interview_mux.creative_delivery import _bed_level_band
    from interview_mux.sound_design import _adaptive_bed_level_db

    lo, hi = _bed_level_band()
    level = _adaptive_bed_level_db(ctx, default_level_db=hi)
    assert lo <= level <= hi
    assert level == lo


def test_repair_sfx_prompts_syncs_plan_duration_to_role_floor(tmp_path, monkeypatch):
    """theme_emphasis craft floor is 6s; SDP must not stay at 5s (craft-vs-plan loop)."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sfx_dur_sync")
    seed_analysis_ready_artifacts(ctx)
    sdp = sound_design_plan_with(
        assets=[
            {
                "asset_id": "show_theme_v1_stinger_01",
                "role": "theme_emphasis",
                "description": "Short emphasis sting.",
                "duration_seconds": 5.0,
            }
        ],
        flow_plans={"podcast": {"profile": "podcast", "cues": []}},
    )
    ctx.write_json("understanding/sound_design_plan.json", sdp, skip_handoff=True)
    from interview_mux.artifact_repairs import repair_sfx_prompts

    repaired, _notes = repair_sfx_prompts(
        ctx,
        {
            "prompts": [
                {
                    "asset_id": "show_theme_v1_stinger_01",
                    "role": "theme_emphasis",
                    "duration_seconds": 5.0,
                    "sfx_prompt": "Warm piano sting, close-mic, no lyrics.",
                    "negative_prompt": "vocals speech lyrics choir talk radio host narrator verse chorus singing",
                }
            ]
        },
    )
    assert float(repaired["prompts"][0]["duration_seconds"]) == 6.0
    plan = ctx.read_json("understanding/sound_design_plan.json")
    assert float(plan["assets"][0]["duration_seconds"]) == 6.0
