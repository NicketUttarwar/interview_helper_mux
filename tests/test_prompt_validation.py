from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.prompt_validation import (
    STAGE_ARTIFACT_SCHEMAS,
    validate_edl,
    validate_stage_artifacts,
)

def _stage_artifacts_fixture() -> dict[str, dict]:
    path = Path(__file__).parent / "fixtures" / "prompts" / "stage_artifacts.json"
    return json.loads(path.read_text(encoding="utf-8"))

@pytest.mark.parametrize("stage_key", sorted(STAGE_ARTIFACT_SCHEMAS))
def test_validate_stage_artifacts_fixture_per_stage_key(stage_key: str):
    fixture_map = _stage_artifacts_fixture()
    artifacts = fixture_map[stage_key]
    assert validate_stage_artifacts(stage_key, artifacts) == []

def test_stage_artifact_fixture_covers_every_stage_key():
    fixture_keys = set(_stage_artifacts_fixture().keys())
    assert fixture_keys == set(STAGE_ARTIFACT_SCHEMAS.keys())

def test_validate_speakers_artifact_ok():
    artifacts = {
        "speakers": [
            {
                "speaker_id": "spk_0",
                "role": "interviewer",
                "confidence": 0.9,
                "evidence": ["asks questions"],
            }
        ]
    }
    assert validate_stage_artifacts("speaker_roles", artifacts) == []

def test_validate_speakers_artifact_missing_role():
    artifacts = {"speakers": [{"speaker_id": "spk_0", "confidence": 0.5}]}
    errors = validate_stage_artifacts("speaker_roles", artifacts)
    assert errors
    assert "role" in errors[0]

def test_validate_sound_design_palettes_artifact_ok():
    artifacts = {
        "coherence": {
            "sonic_identity": "Warm documentary tone with speech-first ducking.",
            "primary_mood": "reflective",
            "density": "sparse",
        },
        "palettes": [
            {
                "palette_id": "origin_story",
                "theme_label": "Origin Story",
                "keywords": ["founder", "early", "risk"],
                "segment_ids": ["seg_001"],
                "ambient_description": "Low, intimate room tone with gentle air movement.",
                "accent_description": "Occasional soft texture no more than once per chapter.",
                "avoid": ["comedy hits", "trailer whooshes", "crowd chants"],
            }
        ],
    }
    assert validate_stage_artifacts("sound_design_palettes", artifacts) == []

def test_validate_sound_design_plan_artifact_ok():
    artifacts = {
        "assets": [
            {
                "asset_id": "chapter_stinger_warm",
                "role": "chapter_stinger",
                "description": "Warm and subtle chapter marker with no vocals.",
                "duration_seconds": 1.5,
                "reuse_note": "Reused at chapter boundaries.",
            }
        ],
        "flow_plans": {
            "podcast": {
                "profile": "podcast",
                "cues": [
                    {
                        "cue_id": "ch_01_end",
                        "asset_id": "chapter_stinger_warm",
                        "placement": "after_segment",
                        "after_segment_id": "seg_010",
                    }
                ],
            }
        },
    }
    assert validate_stage_artifacts("sound_design_plan", artifacts) == []

def test_validate_edl_minimal_ok():
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_a"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "timeline_start_ms": 0,
                "duration_ms": 1000,
            }
        ],
        "timeline_duration_ms": 1000,
    }
    assert validate_edl(edl) == []

def test_validate_edl_narrative_audit_artifact_ok():
    artifacts = {
        "verdict": "pass",
        "blocking_issues": [],
        "warnings": [],
        "recommended_actions": [],
        "reasoning_summary": "Timeline preserves the planned arc.",
    }
    assert validate_stage_artifacts("edl_narrative_audit", artifacts) == []

SAP_PROMPT_FILES = [
    Path("docs/prompts/sound_design/plan-flow1.system.txt"),
    Path("docs/prompts/sound_design/theme-palettes.system.txt"),
    Path("docs/prompts/assembly/podcast-sfx-brief.system.txt"),
]

@pytest.mark.parametrize("prompt_path", SAP_PROMPT_FILES, ids=[p.name for p in SAP_PROMPT_FILES])
def test_sap_prompt_files_mention_pace_class_and_underscore_policy(prompt_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    text = (repo_root / prompt_path).read_text(encoding="utf-8")
    assert "pace_class" in text
    assert "underscore_policy" in text
