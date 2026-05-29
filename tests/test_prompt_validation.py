from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.prompt_validation import (
    STAGE_ARTIFACT_SCHEMAS,
    validate_edl_flow1,
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


def test_validate_show_description_word_count_band():
    artifacts = {
        "description_markdown": "x" * 500,
        "word_count": 200,
        "hook_sentence": "A compelling opening line for listeners.",
        "themes_highlighted": ["growth"],
        "audience_pitch": "Anyone curious about product leadership.",
        "evidence_segment_ids": ["seg_001"],
        "tone": "conversational",
        "confidence": 0.85,
    }
    assert validate_stage_artifacts("podcast_show_description", artifacts) == []


def test_validate_show_description_rejects_low_word_count():
    artifacts = {
        "description_markdown": "Too short.",
        "word_count": 50,
        "hook_sentence": "Short hook here for test.",
        "themes_highlighted": ["topic"],
        "audience_pitch": "Test audience pitch line here.",
        "evidence_segment_ids": ["seg_001"],
        "tone": "journalistic",
        "confidence": 0.5,
    }
    errors = validate_stage_artifacts("podcast_show_description", artifacts)
    assert errors
    assert any("word_count" in e or "description_markdown" in e for e in errors)


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


def test_validate_sound_design_plan_flow1_artifact_ok():
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
            "flow1": {
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
    assert validate_stage_artifacts("sound_design_plan_flow1", artifacts) == []


def test_validate_sound_design_plan_flow2_artifact_ok():
    artifacts = {
        "assets": [
            {
                "asset_id": "montage_transition_glue",
                "role": "transition_stinger",
                "description": "Short forward-motion transition with no vocals.",
                "duration_seconds": 1.4,
                "reuse_note": "Shared between all between_clips cues.",
            }
        ],
        "flow_plans": {
            "flow2": {
                "profile": "montage",
                "cues": [
                    {
                        "cue_id": "cut_1_2",
                        "asset_id": "montage_transition_glue",
                        "placement": "between_clips",
                        "from_clip_rank": 1,
                        "to_clip_rank": 2,
                    }
                ],
            }
        },
    }
    assert validate_stage_artifacts("sound_design_plan_flow2", artifacts) == []


def test_validate_edl_flow1_minimal_ok():
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
    assert validate_edl_flow1(edl) == []


def test_validate_highlights_requires_diversity_bonus():
    artifacts = {
        "highlights": [
            {
                "rank": 1,
                "segment_id": "seg_1",
                "start_ms": 0,
                "end_ms": 1000,
                "headline": "Hook",
                "scores": {"salience": 8, "clarity": 8, "emotion": 7, "quotability": 7},
            }
        ],
        "reel_thesis": "Test",
    }
    errors = validate_stage_artifacts("highlight_selection", artifacts)
    assert any("diversity_bonus" in e for e in errors)
