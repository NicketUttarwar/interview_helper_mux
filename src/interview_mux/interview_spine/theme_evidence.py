from __future__ import annotations

from typing import Any


def attach_theme_evidence_windows(ctx, state: dict[str, Any]) -> None:
    """H-G0-03: attach retrieval-backed evidence windows to themes when spine exists."""
    from interview_mux.interview_spine.config import spine_enabled
    from interview_mux.interview_spine.retrieval import query_spine

    if not spine_enabled():
        return
    themes = state.get("themes")
    if not isinstance(themes, list):
        return
    for theme in themes:
        if not isinstance(theme, dict):
            continue
        label = str(theme.get("label") or theme.get("summary") or "").strip()
        if not label:
            continue
        hits = query_spine(ctx, label, top_k=3)
        if not hits:
            continue
        theme["evidence_windows"] = [
            {
                "window_id": hit.get("window_id"),
                "start_ms": hit.get("start_ms"),
                "end_ms": hit.get("end_ms"),
                "retrieval_score": hit.get("score"),
            }
            for hit in hits
            if isinstance(hit, dict) and hit.get("window_id")
        ]
