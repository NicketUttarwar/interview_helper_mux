"""BUILD-SFX-01 — sonic context, mmaudio_qa, placement schema validation."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.prompt_validation import (
    validate_mmaudio_qa,
    validate_placement_adjustments,
    validate_sonic_context,
    validate_sound_design_plan,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sonic_context"


def test_validate_sonic_context_fixture_ok():
    doc = json.loads((FIXTURES / "one_on_one.json").read_text(encoding="utf-8"))
    assert validate_sonic_context(doc) == []


def test_validate_sonic_context_sparse_mode_allows_empty_registry():
    doc = json.loads((FIXTURES / "one_on_one.json").read_text(encoding="utf-8"))
    doc["tag_registry"] = []
    doc["sparse_mode"] = True
    assert validate_sonic_context(doc) == []


def test_validate_mmaudio_qa_minimal_ok():
    doc = {
        "version": 1,
        "assets": [
            {
                "asset_id": "chapter_stinger_warm",
                "role": "chapter_stinger",
                "verdict": "pass",
                "generation_status": "pass",
                "theme_fit_score": 0.82,
                "silence_detected": False,
            }
        ],
    }
    assert validate_mmaudio_qa(doc) == []


def test_validate_mmaudio_qa_accepts_extended_fields():
    doc = {
        "version": 1,
        "assets": [
            {
                "asset_id": "ambient_farm",
                "role": "ambient_bed",
                "verdict": "warn",
                "generation_status": "pass",
                "loop_seam_score": 0.71,
                "theme_fit_score": 0.55,
                "recommended_action": "refine",
                "reasons": ["bed_too_quiet"],
            }
        ],
    }
    assert validate_mmaudio_qa(doc) == []


def test_validate_placement_adjustments_with_provenance():
    doc = {
        "version": 1,
        "adjustments": [
            {
                "asset_id": "ambient_farm",
                "cue_id": "bed_seg_018",
                "action": "lower_level",
                "reason": "panel overlap segment",
                "suggested_level_db_delta": -3,
                "provenance": {
                    "rule_id": "panel_skip_overlap",
                    "source_artifact": "understanding/sonic_context.json",
                    "detail": "seg_018 in segment_flags.overlap_high",
                },
                "scenario_override": True,
                "adaptive_level_source": "sap_percentile",
            }
        ],
    }
    assert validate_placement_adjustments(doc) == []


def test_validate_sound_design_plan_optional_sonic_fields():
    plan = {
        "version": 1,
        "coherence": {
            "sonic_identity": "warm documentary",
            "primary_mood": "reflective",
            "density": "sparse",
            "scenario_bucket": "one_on_one",
            "tag_lineage": ["founder_origin"],
            "sonic_context_hash": "abc123",
        },
        "palettes": [
            {
                "palette_id": "origin",
                "theme_label": "Origin",
                "keywords": ["founder"],
                "segment_ids": ["seg_001"],
                "ambient_description": "soft room tone",
                "accent_description": "rare texture",
                "avoid": ["whoosh"],
                "tag_ids": ["founder_origin"],
                "sonic_bucket": "ambient_territory",
            }
        ],
        "assets": [
            {
                "asset_id": "stinger_warm",
                "role": "chapter_stinger",
                "description": "soft rise",
                "duration_seconds": 1.5,
                "tag_ids": ["founder_origin"],
                "cue_opportunity_refs": ["chapter_boundary:seg_010"],
            }
        ],
        "flow_plans": {
            "podcast": {"profile": "podcast", "cues": []},
            "flow2": {"profile": "montage", "cues": []},
        },
        "generated": {},
    }
    assert validate_sound_design_plan(plan) == []


def test_sdp_cross_validate_post_sonic_context(tmp_path, monkeypatch):
    from interview_mux.sdp_cross_validate import validate_post_sonic_context
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_sonic_ctx")
    assert validate_post_sonic_context(ctx) == ["understanding/sonic_context.json missing"]

    doc = json.loads((FIXTURES / "one_on_one.json").read_text(encoding="utf-8"))
    ctx.write_json("understanding/sonic_context.json", doc, skip_handoff=True)
    assert validate_post_sonic_context(ctx) == []


def test_sdp_cross_validate_post_mmaudio_qa_contradiction(tmp_path, monkeypatch):
    from interview_mux.sdp_cross_validate import validate_post_mmaudio_qa
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "run_mmaudio_qa")
    assert validate_post_mmaudio_qa(ctx) == []

    ctx.write_json(
        "sound_design/mmaudio_qa.json",
        {
            "version": 1,
            "assets": [
                {
                    "asset_id": "bed_a",
                    "verdict": "pass",
                    "generation_status": "placeholder",
                }
            ],
        },
        skip_handoff=True,
    )
    errors = validate_post_mmaudio_qa(ctx)
    assert any("generation_status=placeholder" in e for e in errors)
