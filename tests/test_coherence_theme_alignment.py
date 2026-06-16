from __future__ import annotations

from interview_mux.coherence.theme_alignment import build_theme_scores, score_window_themes


def test_theme_alignment_token_overlap():
    win = {"window_id": "w1", "start_ms": 0, "end_ms": 5000, "text_span": "platform strategy growth metrics"}
    topics = [{"name": "Platform strategy", "summary": "How the product scales"}]
    alignment, theme_id = score_window_themes(win, topics)
    assert alignment >= 0.33
    assert theme_id == "Platform strategy"


def test_build_theme_scores_second_half_drift():
    brief = {"topics": [{"name": "Finance", "summary": "Revenue model"}]}
    windows = [
        {"window_id": "w1", "start_ms": 0, "end_ms": 5000, "text_span": "unrelated sports talk"},
        {"window_id": "w2", "start_ms": 20_000_000, "end_ms": 20_005_000, "text_span": "random aside"},
    ]
    rows = build_theme_scores(windows, brief, duration_ms=40_000_000)
    assert rows[1]["drift_score"] >= rows[0]["drift_score"]
