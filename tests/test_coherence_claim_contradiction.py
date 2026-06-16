from __future__ import annotations

from interview_mux.coherence.claim_contradiction import detect_claim_contradictions


def test_planted_contradiction_with_negation():
    brief = {
        "key_claims": [{"id": "c1", "claim": "We always ship on schedule"}],
        "topic_relationships": [],
    }
    windows = [
        {"window_id": "w_early", "start_ms": 600_000, "text_span": "We always ship on schedule"},
        {
            "window_id": "w_late",
            "start_ms": 22 * 60 * 1000,
            "text_span": "We never actually ship on schedule — correction from last year",
        },
    ]
    risks = detect_claim_contradictions(
        content_brief=brief,
        windows=windows,
        duration_ms=31 * 60 * 1000,
        threshold=0.5,
        blocking=True,
    )
    assert any(r["kind"] == "claim_contradiction" for r in risks)
    assert any(r.get("blocking") for r in risks)
