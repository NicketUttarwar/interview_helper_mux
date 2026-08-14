"""Tests for creative delivery policy (SFX/music + editorial shaping)."""

from __future__ import annotations

from interview_mux.creative_delivery import (
    apply_creative_mix_contract,
    hydrate_flow_cue_segments,
    validate_creative_density,
    validate_cue_segment_anchors,
)
from run_fixtures import isolated_run_ctx, seed_analysis_ready_artifacts, sound_design_plan_with


def test_hydrate_cue_segments_from_cue_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_hydrate_cues")
    seed_analysis_ready_artifacts(ctx)
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
        {"underscore_policy": "sparse", "bed_level_db_range": [-30, -26], "duck_under_speech_db": 16}
    )
    assert out["underscore_policy"] == "normal"
    # Creative path forces audible bed band (−25…−21 by default).
    assert out["bed_level_db_range"][0] >= -25
    assert out["bed_level_db_range"][1] >= -21
    assert out["duck_under_speech_db"] >= 20


def test_audibility_level_db_role_aware():
    from interview_mux.creative_delivery import audibility_level_db

    bed = audibility_level_db(role="bed", default=-30.0)
    assert -25.0 <= bed <= -21.0
    cold = audibility_level_db(role="theme_cold_open", default=-20.0)
    assert cold >= -9.0
    emph = audibility_level_db(role="theme_emphasis", default=-20.0)
    assert emph >= -15.0
