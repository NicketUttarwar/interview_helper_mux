from __future__ import annotations

from typing import Any

from interview_mux.disfluency.config import disfluency_enabled
from interview_mux.run_context import RunContext

_SUMMARY_EVENT_CAP = 40


def disfluency_summary_for_ctx(ctx: RunContext) -> dict[str, Any] | None:
    """Compact filler catalog for LLM stages (after extract / review artifacts exist)."""
    if not disfluency_enabled():
        return None
    if not ctx.artifact_exists("transcript/disfluencies.json"):
        return None
    try:
        doc = ctx.read_json("transcript/disfluencies.json")
    except Exception:
        return None
    if not isinstance(doc, dict) or str(doc.get("status")) in {"skipped", "disabled", "no_assets"}:
        return None

    events = [e for e in (doc.get("events") or []) if isinstance(e, dict)]
    if not events:
        return None

    confirmed = [e for e in events if e.get("review_status") == "confirmed"]
    restore_ids = {
        str(e.get("event_id"))
        for e in confirmed
        if e.get("include_in_restore") is not False and e.get("event_id")
    }

    def _compact(ev: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": ev.get("event_id"),
            "start_ms": ev.get("start_ms"),
            "end_ms": ev.get("end_ms"),
            "speaker_id": ev.get("speaker_id"),
            "text": str(ev.get("text") or "")[:40],
            "source": ev.get("source"),
            "review_status": ev.get("review_status"),
            "include_in_restore": ev.get("include_in_restore", True),
        }

    per_segment: dict[str, int] = {}
    for ev in confirmed:
        sid = str(ev.get("segment_id") or "")
        if not sid and ctx.artifact_exists("segments/manifest.json"):
            es = int(ev.get("start_ms") or 0)
            manifest = ctx.read_json("segments/manifest.json")
            for seg in manifest.get("segments") or []:
                if not isinstance(seg, dict):
                    continue
                ss = int(seg.get("start_ms") or 0)
                ee = int(seg.get("end_ms") or ss)
                if ss <= es < ee:
                    sid = str(seg.get("segment_id") or "")
                    break
        if sid:
            per_segment[sid] = per_segment.get(sid, 0) + 1

    review_complete = ctx.is_done("disfluency_review")

    return {
        "stats": doc.get("stats") or {},
        "review_complete": review_complete,
        "confirmed_count": len(confirmed),
        "restore_eligible_count": len(restore_ids),
        "confirmed_events": [_compact(e) for e in confirmed[:_SUMMARY_EVENT_CAP]],
        "pending_count": sum(1 for e in events if e.get("review_status") == "pending"),
        "per_segment_confirmed": per_segment,
        "note": (
            "Operator-reviewed filler words (um, uh, …) detected in source audio. "
            "Use for pacing/authenticity — not for inventing quotes. "
            "Events with include_in_restore may be spliced into Flow 1 assembly audio "
            "when disfluency_restore is enabled; ranking should treat content meaning, not filler density, as primary."
        ),
    }


def attach_disfluency_context(payload: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    summary = disfluency_summary_for_ctx(ctx)
    if summary:
        payload["disfluency_catalog"] = summary
    return payload
