from interview_mux.prompt_validation import validate_stage_artifacts


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
