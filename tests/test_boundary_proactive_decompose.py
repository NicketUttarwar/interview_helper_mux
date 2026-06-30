from __future__ import annotations

from interview_mux.llm_shard_plans import should_proactive_decompose_boundary_detection


def test_should_proactive_decompose_on_oversplit_hint() -> None:
    stage_input = {
        "pause_ladder_hints": {
            "candidates": [{"threshold_ms": 400, "count": 60}],
            "pace_class": "calm",
        },
        "transcript_words": [{"word": "hello", "start_ms": 0, "end_ms": 100}] * 200,
    }
    assert should_proactive_decompose_boundary_detection(stage_input) is True


def test_should_not_proactive_decompose_when_small() -> None:
    stage_input = {
        "pause_ladder_hints": {
            "candidates": [{"threshold_ms": 400, "count": 10}],
            "pace_class": "calm",
        },
        "transcript_words": [{"word": "hi", "start_ms": 0, "end_ms": 50}] * 20,
    }
    assert should_proactive_decompose_boundary_detection(stage_input) is False
