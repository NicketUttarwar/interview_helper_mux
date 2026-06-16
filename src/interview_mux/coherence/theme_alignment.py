from __future__ import annotations

import re
from typing import Any


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9']+", text.lower()) if len(t) > 2}


def score_window_themes(
    window: dict[str, Any],
    topics: list[dict[str, Any]],
) -> tuple[float, str | None]:
    """Token overlap alignment; returns (theme_alignment, best_theme_id)."""
    text = str(window.get("text_span") or "")
    w_tokens = _tokenize(text)
    if not w_tokens or not topics:
        return 0.0, None

    best_score = 0.0
    best_id: str | None = None
    for idx, topic in enumerate(topics):
        if not isinstance(topic, dict):
            continue
        label = f"{topic.get('name', '')} {topic.get('summary', '')}"
        t_tokens = _tokenize(label)
        if not t_tokens:
            continue
        overlap = len(w_tokens & t_tokens) / len(t_tokens)
        if overlap > best_score:
            best_score = overlap
            best_id = str(topic.get("id") or topic.get("name") or f"topic_{idx}")
    return round(min(1.0, best_score), 4), best_id


def build_theme_scores(
    windows: list[dict[str, Any]],
    content_brief: dict[str, Any],
    *,
    duration_ms: int,
) -> list[dict[str, Any]]:
    topics = content_brief.get("topics") or []
    half_ms = duration_ms // 2 if duration_ms else 0
    rows: list[dict[str, Any]] = []
    for win in windows:
        alignment, theme_id = score_window_themes(win, topics)
        start_ms = int(win.get("start_ms", 0))
        drift = 1.0 - alignment if half_ms and start_ms >= half_ms else max(0.0, 1.0 - alignment) * 0.5
        rows.append(
            {
                "window_id": win.get("window_id"),
                "start_ms": start_ms,
                "end_ms": int(win.get("end_ms", 0)),
                "theme_alignment": alignment,
                "best_theme_id": theme_id,
                "drift_score": round(drift, 4),
            }
        )
    return rows
