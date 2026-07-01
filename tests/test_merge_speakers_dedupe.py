"""Speakers merge dedupe tests."""

from __future__ import annotations

from interview_mux.artifact_completeness import merge_artifact


def test_merge_speakers_dedupes_by_speaker_id():
    existing = {
        "speakers": [
            {"speaker_id": "spk_0", "role": "unknown", "confidence": 0.5},
            {"speaker_id": "spk_1", "role": "unknown", "confidence": 0.5},
        ]
    }
    patch = {
        "speakers": [
            {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
            {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.95},
        ]
    }
    merged = merge_artifact("understanding/speakers.json", existing, patch)
    ids = [s["speaker_id"] for s in merged["speakers"]]
    assert ids.count("spk_0") == 1
    assert merged["speakers"][0]["role"] == "interviewer"
