from __future__ import annotations

from typing import Any

from interview_mux.interview_spine.paths import SPINE_PATH

STAGE_SPINE_VOLLEY_KEYS = frozenset(
    {
        "boundary_detection",
        "segment_classification",
        "missing_framing",
        "content_context",
        "highlight_selection",
        "full_master_ranking",
    }
)

_STAGE_SPINE_LIMITS: dict[str, dict[str, int]] = {
    "content_context": {"max_windows": 2, "max_events": 8, "max_chars": 100},
    "segment_classification": {"max_windows": 3, "max_events": 10, "max_chars": 120},
    "missing_framing": {"max_windows": 4, "max_events": 15, "max_chars": 120},
    "highlight_selection": {"max_windows": 5, "max_events": 12, "max_chars": 140},
    "full_master_ranking": {"max_windows": 3, "max_events": 10, "max_chars": 120},
}


def attach_spine_to_payload(ctx, payload: dict[str, Any], stage_key: str) -> None:
    from interview_mux.interview_spine.config import spine_enabled

    if not spine_enabled() or stage_key not in STAGE_SPINE_VOLLEY_KEYS:
        return
    if stage_key == "boundary_detection":
        compact = compact_for_boundary(ctx)
    else:
        limits = _STAGE_SPINE_LIMITS.get(stage_key, {"max_windows": 3, "max_events": 8, "max_chars": 120})
        compact = compact_for_volley(
            ctx,
            max_windows=limits["max_windows"],
            max_chars=limits["max_chars"],
        )
        if compact and limits.get("max_events"):
            compact["top_boundary_events"] = (compact.get("top_boundary_events") or [])[: limits["max_events"]]
    if compact:
        payload["interview_spine"] = compact


def load_spine(ctx) -> dict[str, Any] | None:
    if not ctx.artifact_exists(SPINE_PATH):
        return None
    doc = ctx.read_json(SPINE_PATH)
    return doc if isinstance(doc, dict) else None


def compact_for_boundary(ctx) -> dict[str, Any] | None:
    spine = load_spine(ctx)
    if not spine:
        return None
    events = list(spine.get("boundary_events") or [])[:40]
    return {
        "window_count": len(spine.get("windows") or []),
        "boundary_events": events,
        "speaker_stats": spine.get("speaker_stats") or [],
    }


def compact_for_volley(ctx, *, max_windows: int = 3, max_chars: int = 120) -> dict[str, Any] | None:
    spine = load_spine(ctx)
    if not spine:
        return None
    windows = []
    for win in (spine.get("windows") or [])[:max_windows]:
        text = str(win.get("text_span") or "")[:max_chars]
        windows.append(
            {
                "window_id": win.get("window_id"),
                "start_ms": win.get("start_ms"),
                "end_ms": win.get("end_ms"),
                "text_span": text,
            }
        )
    return {
        "retrieval_enabled": bool((spine.get("retrieval") or {}).get("enabled")),
        "windows_sample": windows,
        "top_boundary_events": (spine.get("boundary_events") or [])[:8],
    }
