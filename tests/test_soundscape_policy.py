"""Tests for soundscape_policy merge, cue slots, and resolve API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_run_soundscape_policy_build_missing_delivery_brief_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SPB-B2: enabled + no delivery_brief → RuntimeError (honest refuse)."""
    patch_mix_test_config(monkeypatch, disable_soundscape=False, disable_creative_delivery=True)
    ctx = isolated_run_ctx(tmp_path, "run_sp_no_brief")
    assert not ctx.artifact_exists("understanding/delivery_brief.json")
    with pytest.raises(RuntimeError, match="requires understanding/delivery_brief.json"):
        run_soundscape_policy_build(ctx)
    assert not ctx.artifact_exists(POLICY_PATH)


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


def test_score_cue_slots_preserves_planned_sdp_beds_beyond_dens_cap(tmp_path) -> None:
    """Coverage-seed beds outside dens max_beds must still get cue_slots.

    refresh_cue_slots rescored with max_beds=1 was wiping 15/16 bed slots
    (exec_13167 sound_design_plan post-commit thrash).
    """
    from interview_mux.analysis_memory import default_sound_design_plan
    from interview_mux.soundscape_policy import refresh_cue_slots
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    ctx = isolated_run_ctx(tmp_path, "run_sp_planned_beds")
    _seed_inputs(ctx)
    # Extra long segments so scoring would only keep 1 under dens=1 without merge.
    _raw_write(
        ctx,
        "segments/manifest.json",
        {
            "segments": [
                {"segment_id": "seg_001", "start_ms": 0, "end_ms": 60000},
                {"segment_id": "seg_002", "start_ms": 60000, "end_ms": 120000},
                {"segment_id": "seg_005", "start_ms": 120000, "end_ms": 180000},
                {"segment_id": "seg_008", "start_ms": 180000, "end_ms": 240000},
            ]
        },
    )
    ctx.write_json(
        "master/selection.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001", "seg_002", "seg_005", "seg_008"],
            "excluded_segment_ids": [],
            "chapters": [],
        },
        skip_handoff=True,
    )
    sdp = default_sound_design_plan()
    sdp["palettes"] = [
        {
            "palette_id": "farm",
            "theme_label": "farm",
            "keywords": ["farm"],
            "segment_ids": ["seg_001", "seg_002", "seg_005", "seg_008"],
            "ambient_description": "soft pasture",
            "accent_description": "birds",
            "avoid": [],
        }
    ]
    sdp["assets"] = [
        {
            "asset_id": "theme_underscore_calm",
            "role": "theme_underscore",
            "description": "calm bed",
            "duration_seconds": 16,
        }
    ]
    sdp["flow_plans"]["podcast"]["cues"] = [
        {
            "cue_id": "bed_coverage_seed_1",
            "placement": "under_segment",
            "segment_id": "seg_005",
            "asset_id": "theme_underscore_calm",
            "role": "theme_underscore",
            "level_db": -28,
        },
        {
            "cue_id": "bed_coverage_seed_2",
            "placement": "under_segment",
            "segment_id": "seg_008",
            "asset_id": "theme_underscore_calm",
            "role": "theme_underscore",
            "level_db": -28,
        },
    ]
    _raw_write(ctx, "understanding/sound_design_plan.json", sdp)
    ctx.write_json(
        POLICY_PATH,
        {
            "version": 1,
            "derived_from": {},
            "underscore_policy": "normal",
            "pace_class": "conversational",
            "sfx_density": {"max_beds": 1, "max_punctuators": 0, "max_foley": 0},
            "mix_contract": {
                "underscore_policy": "normal",
                "bed_level_db_range": [-30, -26],
            },
            "standards": {},
            "cue_slots": [
                {
                    "slot_id": "bed_seg_001",
                    "segment_id": "seg_001",
                    "placement": "under_segment",
                    "allowed_roles": ["theme_underscore"],
                    "priority": 0.9,
                    "reason": "seed",
                }
            ],
            "operator_overrides": {},
            "rationale": [],
            "policy_hash": "test",
        },
        skip_handoff=True,
    )

    scored = score_cue_slots(
        ctx,
        underscore="normal",
        pace="conversational",
        dens={"max_beds": 1, "max_punctuators": 0, "max_foley": 0},
        mix_contract={"bed_level_db_range": [-30, -26]},
    )
    bed_segs = {
        str(s.get("segment_id"))
        for s in scored
        if "theme_underscore" in (s.get("allowed_roles") or [])
    }
    assert "seg_005" in bed_segs
    assert "seg_008" in bed_segs

    enter_stage_staging("sound_design_plan")
    try:
        refreshed = refresh_cue_slots(ctx)
    finally:
        exit_stage_staging()
    refreshed_beds = {
        str(s.get("segment_id"))
        for s in (refreshed.get("cue_slots") or [])
        if isinstance(s, dict)
        and "theme_underscore" in (s.get("allowed_roles") or [])
    }
    assert "seg_005" in refreshed_beds
    assert "seg_008" in refreshed_beds
    # Persist must land on committed policy even under SDP staging.
    committed = load_policy(ctx) or {}
    committed_beds = {
        str(s.get("segment_id"))
        for s in (committed.get("cue_slots") or [])
        if isinstance(s, dict)
        and "theme_underscore" in (s.get("allowed_roles") or [])
    }
    assert "seg_005" in committed_beds
    assert "seg_008" in committed_beds


def test_normalize_cue_slot_fills_canonical_fields() -> None:
    from interview_mux.soundscape_policy import normalize_cue_slot

    raw = {
        "segment_id": "seg_9",
        "allowed_roles": "theme_underscore",
        "reason": "theme_underscore_palette_bed_slot",
    }
    slot = normalize_cue_slot(raw, bed_level=-28.0)
    assert slot is not None
    assert slot["slot_id"] == "bed_seg_9"
    assert slot["placement"] == "under_segment"
    assert slot["allowed_roles"] == ["theme_underscore"]
    assert slot["max_level_db"] == -28.0
    assert slot["origin"] == "inject"
    assert isinstance(slot["priority"], float)


def test_invent_soft_block_keeps_planned_beds(tmp_path, monkeypatch) -> None:
    """Unpaid invent must not wipe planned SDP beds (Partial Zero A+)."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.soundscape_policy import _apply_invent_obligation_gate

    status = {
        "unpaid": True,
        "waived": False,
        "invent": "sound_design_plan",
        "pals": 0,
        "cues": 0,
    }
    policy = {
        "sfx_density": {"max_beds": 4},
        "mix_contract": {
            "underscore_policy": "normal",
            "bed_level_db_range": [-30, -26],
            "max_bed_coverage_ratio": 0.8,
        },
        "underscore_policy": "normal",
        "standards": {},
        "cue_slots": [
            {
                "slot_id": "bed_seg_005",
                "segment_id": "seg_005",
                "placement": "under_segment",
                "allowed_roles": ["theme_underscore"],
                "priority": 0.55,
                "max_level_db": -28.0,
                "reason": "planned_sdp_bed",
                "origin": "planned",
            },
            {
                "slot_id": "bed_seg_001",
                "segment_id": "seg_001",
                "placement": "under_segment",
                "allowed_roles": ["theme_underscore"],
                "priority": 0.4,
                "max_level_db": -28.0,
                "reason": "duration_ok",
                "origin": "dens",
            },
        ],
        "rationale": [],
    }
    gated = _apply_invent_obligation_gate(policy, status=status, rationale=[])
    assert gated.get("invent_gate") == "blocked"
    segs = {
        str(s.get("segment_id"))
        for s in (gated.get("cue_slots") or [])
        if isinstance(s, dict)
    }
    assert "seg_005" in segs
    assert "seg_001" not in segs


def test_admit_inject_cue_slots_ssot(tmp_path) -> None:
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.soundscape_policy import admit_inject_cue_slots

    ctx = isolated_run_ctx(tmp_path, "run_sp_inject")
    _seed_inputs(ctx)
    policy = {
        "sfx_density": {"max_beds": 2, "max_punctuators": 0, "max_foley": 0},
        "mix_contract": {"bed_level_db_range": [-30, -26]},
        "underscore_policy": "normal",
        "pace_class": "conversational",
        "cue_slots": [],
        "rationale": [],
    }
    out = admit_inject_cue_slots(
        ctx,
        policy,
        segment_ids=["seg_002"],
        reason="theme_underscore_palette_bed_slot",
        persist=False,
        rescore=False,
    )
    beds = [
        s
        for s in (out.get("cue_slots") or [])
        if isinstance(s, dict) and s.get("segment_id") == "seg_002"
    ]
    assert len(beds) == 1
    assert beds[0].get("origin") == "inject"
    assert beds[0].get("max_level_db") is not None
    assert "origin" in beds[0]

