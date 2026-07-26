"""Tests for soundscape_policy merge, cue slots, and resolve API."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.soundscape_policy import (
    POLICY_PATH,
    build_policy,
    load_policy,
    resolve_mix_contract,
    run_soundscape_policy_build,
    save_operator_overrides,
    score_cue_slots,
)
from run_fixtures import isolated_run_ctx, minimal_source_acoustic_profile, patch_mix_test_config


def _raw_write(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _seed_inputs(ctx, *, underscore: str = "normal", pace: str = "conversational", music_risk: str = "low") -> None:
    sap = minimal_source_acoustic_profile(
        pacing={
            "global_wpm": 140,
            "wpm_by_quartile": [120, 130, 140, 150],
            "pace_class": pace,
            "speech_active_ratio": 0.7,
            "overlap_proxy": 0.05,
        },
        source_music_risk=music_risk,
        mix_contract={
            "underscore_policy": underscore,
            "duck_under_speech_db": 16,
            "stinger_max_per_minute": 3,
            "bed_level_db_range": [-30, -26],
        },
    )
    ctx.write_json("understanding/source_acoustic_profile.json", sap)
    fixture = Path(__file__).parent / "fixtures" / "sonic_context" / "one_on_one.json"
    sonic = json.loads(fixture.read_text(encoding="utf-8"))
    sonic["mix_policy"]["underscore_policy"] = underscore
    _raw_write(ctx, "understanding/sonic_context.json", sonic)
    ctx.write_json(
        "understanding/delivery_brief.json",
        {
            "version": 1,
            "source_duration_ms": 600000,
            "target_duration_sec": {"min": 300, "ideal": 420, "max": 540},
            "question_budget": {"min": 0, "ideal": 2, "max": 4},
            "chapter_budget": {"min": 2, "ideal": 3, "max": 4},
            "selection_mode": "coverage_first",
            "sfx_density": {"max_beds": 2, "max_punctuators": 2, "max_foley": 1},
            "ranking_weights": {},
            "rationale": [],
            "operator_overrides": {},
            "generated": {},
        },
    )
    _raw_write(
        ctx,
        "segments/manifest.json",
        {
            "segments": [
                {"segment_id": "seg_001", "start_ms": 0, "end_ms": 20000},
                {"segment_id": "seg_002", "start_ms": 20000, "end_ms": 45000},
            ]
        },
    )
    from interview_mux.analysis_memory import default_sound_design_plan

    sdp = default_sound_design_plan()
    sdp["palettes"] = [
        {
            "palette_id": "farm",
            "theme_label": "farm",
            "keywords": ["farm", "crops"],
            "segment_ids": ["seg_001", "seg_002"],
            "ambient_description": "soft morning pasture",
            "accent_description": "distant birds",
            "avoid": ["cartoon barn"],
        }
    ]
    _raw_write(ctx, "understanding/sound_design_plan.json", sdp)


def test_build_policy_skips_beds_on_skip(tmp_path, monkeypatch) -> None:
    patch_mix_test_config(monkeypatch, disable_soundscape=False, disable_creative_delivery=True)
    ctx = isolated_run_ctx(tmp_path, "run_sp_skip")
    _seed_inputs(ctx, underscore="skip")
    policy = build_policy(ctx)
    assert policy["underscore_policy"] == "skip"
    assert policy["sfx_density"]["max_beds"] == 0
    assert all("ambient_bed" not in (s.get("allowed_roles") or []) for s in policy["cue_slots"])


def test_build_policy_high_music_risk_forces_skip(tmp_path, monkeypatch) -> None:
    patch_mix_test_config(monkeypatch, disable_soundscape=False, disable_creative_delivery=True)
    ctx = isolated_run_ctx(tmp_path, "run_sp_music")
    _seed_inputs(ctx, underscore="normal", music_risk="high")
    policy = build_policy(ctx)
    assert policy["underscore_policy"] == "skip"
    assert policy["sfx_density"]["max_beds"] == 0


def test_run_soundscape_policy_build_persists(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sp_build")
    _seed_inputs(ctx)
    run_soundscape_policy_build(ctx)
    assert ctx.artifact_exists(POLICY_PATH)
    loaded = load_policy(ctx)
    assert loaded is not None
    assert loaded.get("policy_hash")
    contract = resolve_mix_contract(ctx)
    assert "bed_level_db_range" in contract
    assert contract["underscore_policy"] in {"normal", "sparse", "skip"}


def test_operator_override_skip(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sp_ov")
    _seed_inputs(ctx, underscore="normal")
    run_soundscape_policy_build(ctx)
    policy = save_operator_overrides(ctx, {"underscore_policy": "skip"})
    assert policy["underscore_policy"] == "skip"
    assert policy["sfx_density"]["max_beds"] == 0


def test_score_cue_slots_theme_match(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sp_slots")
    _seed_inputs(ctx)
    slots = score_cue_slots(
        ctx,
        underscore="normal",
        pace="conversational",
        dens={"max_beds": 2, "max_punctuators": 1, "max_foley": 0},
        mix_contract={"bed_level_db_range": [-30, -26]},
    )
    assert any(s.get("placement") == "under_segment" for s in slots)
