from __future__ import annotations

from typing import Any

from interview_mux.interview_spine.constants import BOUNDARY_VOLLEY_MAX_SPINE_EVENTS
from interview_mux.coverage_limits import volley_spine_event_cap
from interview_mux.interview_spine.paths import SPINE_PATH

STAGE_SPINE_VOLLEY_KEYS = frozenset(
    {
        "boundary_detection",
        "segment_classification",
        "missing_framing",
        "content_context",
        "full_master_ranking",
    }
)

_STAGE_SPINE_LIMITS: dict[str, dict[str, int]] = {
    "content_context": {"max_windows": 2, "max_events": 8, "max_chars": 100},
    "segment_classification": {"max_windows": 3, "max_events": 10, "max_chars": 120},
    "missing_framing": {"max_windows": 4, "max_events": 15, "max_chars": 120},
    "full_master_ranking": {"max_windows": 3, "max_events": 10, "max_chars": 120},
}

def attach_spine_to_payload(ctx, payload: dict[str, Any], stage_key: str) -> None:
    from interview_mux.interview_spine.config import spine_enabled

    if not spine_enabled() or stage_key not in STAGE_SPINE_VOLLEY_KEYS:
        return
    if stage_key == "boundary_detection":
        from interview_mux.boundary_observability import oversplit_risk_from_hints, pace_class_from_sap

        pace = pace_class_from_sap(ctx)
        hints = payload.get("pause_ladder_hints")
        oversplit = oversplit_risk_from_hints(hints) if isinstance(hints, dict) else False
        compact = compact_for_boundary(ctx, pace_class=pace, oversplit=oversplit)
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

def rank_boundary_events(
    events: list[dict[str, Any]],
    *,
    pace_class: str = "conversational",
    oversplit: bool = False,
    cap: int | None = None,
) -> list[dict[str, Any]]:
    """Spread-ranked selection of boundary events for volley (not head-biased)."""
    effective_cap = cap if cap is not None else BOUNDARY_VOLLEY_MAX_SPINE_EVENTS
    if len(events) <= effective_cap:
        return list(events)
    spread_cap = volley_spine_event_cap(len(events))
    effective_cap = min(effective_cap, spread_cap) if spread_cap > 0 else effective_cap
    prefer_long = pace_class in ("calm", "dense") or oversplit

    def _score(ev: dict[str, Any]) -> float:
        tier = int(ev.get("threshold_ms") or ev.get("pause_ms") or 0)
        score = float(ev.get("confidence") or 0.5)
        if prefer_long:
            if tier >= 1200:
                score += 2.0
            elif tier >= 700:
                score += 1.0
            elif tier <= 400:
                score -= 0.5
        start = int(ev.get("start_ms") or ev.get("time_ms") or 0)
        return score + (start / 1_000_000_000.0)

    scored = sorted(
        [e for e in events if isinstance(e, dict)],
        key=_score,
        reverse=True,
    )
    if not scored:
        return []

    max_ms = max(int(e.get("start_ms") or e.get("time_ms") or 0) for e in scored) or 1
    buckets = max(4, min(12, effective_cap // 3))
    bin_size = max(max_ms // buckets, 1)
    per_bin: dict[int, list[dict[str, Any]]] = {}
    for ev in scored:
        start = int(ev.get("start_ms") or ev.get("time_ms") or 0)
        b = min(start // bin_size, buckets - 1)
        per_bin.setdefault(b, []).append(ev)

    picked: list[dict[str, Any]] = []
    seen_starts: set[int] = set()
    while len(picked) < effective_cap:
        progressed = False
        for b in sorted(per_bin.keys()):
            if not per_bin[b]:
                continue
            ev = per_bin[b].pop(0)
            start = int(ev.get("start_ms") or ev.get("time_ms") or 0)
            if start in seen_starts:
                continue
            seen_starts.add(start)
            picked.append(ev)
            progressed = True
            if len(picked) >= effective_cap:
                break
        if not progressed:
            break

    picked.sort(key=lambda e: int(e.get("start_ms") or e.get("time_ms") or 0))
    return picked[:effective_cap]

def compact_for_boundary(ctx, *, pace_class: str = "conversational", oversplit: bool = False) -> dict[str, Any] | None:
    spine = load_spine(ctx)
    if not spine:
        return None
    raw_events = list(spine.get("boundary_events") or [])
    events = rank_boundary_events(
        raw_events,
        pace_class=pace_class,
        oversplit=oversplit,
    )
    meta: dict[str, Any] = {}
    if len(raw_events) > len(events):
        meta = {
            "thinning_applied": True,
            "omitted_count": len(raw_events) - len(events),
            "selection_strategy": "ranked_spread",
        }
    return {
        "window_count": len(spine.get("windows") or []),
        "boundary_events": events,
        "speaker_stats": spine.get("speaker_stats") or [],
        **meta,
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
