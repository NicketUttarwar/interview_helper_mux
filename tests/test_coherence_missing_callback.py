from __future__ import annotations

from interview_mux.coherence.missing_callback import detect_missing_callbacks


def test_missing_callback_when_topic_not_returned():
    brief = {
        "topics": [
            {"name": "Origin story", "segment_ids": ["seg_001"]},
            {"name": "Future vision", "segment_ids": ["seg_002"]},
        ],
        "topic_relationships": [{"from_topic": "Origin story", "to_topic": "Future vision", "relation": "returns_to"}],
    }
    manifest = {
        "segments": [
            {"segment_id": "seg_001", "start_ms": 0, "end_ms": 600_000},
            {"segment_id": "seg_002", "start_ms": 700_000, "end_ms": 900_000},
        ]
    }
    windows = [
        {"window_id": "w1", "start_ms": 0, "end_ms": 5000, "text_span": "origin story beginning"},
        {"window_id": "w2", "start_ms": 20 * 60 * 1000, "end_ms": 20 * 60 * 1000 + 5000, "text_span": "other topic only"},
    ]
    risks = detect_missing_callbacks(
        content_brief=brief,
        windows=windows,
        manifest=manifest,
        duration_ms=31 * 60 * 1000,
        threshold=0.6,
    )
    assert any(r["kind"] == "missing_callback" for r in risks)
