from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.disfluency.config import disfluency_enabled
from interview_mux.disfluency.extract import (
    load_disfluencies,
    recompute_stats,
    run_extraction,
    write_disabled_artifact,
)
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext


def run_disfluency_extract(ctx: RunContext) -> None:
    if not disfluency_enabled():
        write_disabled_artifact(ctx)
        ctx.log("disfluency_extract skipped (disabled in config).", level="info", stage="disfluency_extract")
        ctx.mark_done("disfluency_extract")
        ctx.mark_done("disfluency_review")
        return

    with logged_step("disfluency_extract/run_extraction", ctx=ctx, stage="disfluency_extract"):
        doc = run_extraction(ctx)
        ctx.write_json("transcript/disfluencies.json", doc)
    total = (doc.get("stats") or {}).get("total", 0)
    ctx.log(
        f"disfluency_extract: wrote {total} event(s) → transcript/disfluencies.json",
        level="success",
        stage="disfluency_extract",
    )
    ctx.mark_done("disfluency_extract")
    if total == 0:
        auto_complete_empty_review(ctx)


def get_review_state(ctx: RunContext) -> dict[str, Any]:
    doc = load_disfluencies(ctx)
    events = [e for e in (doc.get("events") or []) if isinstance(e, dict)]
    pending = sum(1 for e in events if e.get("review_status") == "pending")
    return {
        "ready": ctx.artifact_exists("transcript/disfluencies.json"),
        "status": doc.get("status"),
        "events": events,
        "stats": doc.get("stats") or {},
        "pending_count": pending,
        "review_complete": ctx.is_done("disfluency_review"),
    }


def _pending_event_count(doc: dict[str, Any]) -> int:
    events = doc.get("events") or []
    return sum(
        1
        for e in events
        if isinstance(e, dict) and e.get("review_status") == "pending"
    )


def maybe_auto_complete_review(ctx: RunContext) -> bool:
    """Sign off disfluency review when the catalog has no pending events."""
    if ctx.is_done("disfluency_review"):
        return False
    if not ctx.artifact_exists("transcript/disfluencies.json"):
        return False
    doc = load_disfluencies(ctx)
    if str(doc.get("status")) in {"skipped", "no_assets", "disabled"}:
        return False
    events = [e for e in (doc.get("events") or []) if isinstance(e, dict)]
    if not events:
        auto_complete_empty_review(ctx)
        return ctx.is_done("disfluency_review")
    if _pending_event_count(doc):
        return False
    mark_disfluency_review_complete(ctx)
    return True


def update_event_review(
    ctx: RunContext,
    event_id: str,
    *,
    review_status: str,
    text: str | None = None,
    include_in_restore: bool | None = None,
) -> dict[str, Any]:
    doc = load_disfluencies(ctx)
    found = False
    for ev in doc.get("events") or []:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("event_id")) != event_id:
            continue
        ev["review_status"] = review_status
        if text is not None:
            ev["text"] = text
        if include_in_restore is not None:
            ev["include_in_restore"] = include_in_restore
        found = True
        break
    if not found:
        raise KeyError(event_id)
    recompute_stats(doc)
    ctx.write_json("transcript/disfluencies.json", doc)
    result: dict[str, Any] = {"ok": True, "stats": doc.get("stats")}
    if maybe_auto_complete_review(ctx):
        result["review_complete"] = True
    return result


def confirm_all_pending(ctx: RunContext) -> None:
    doc = load_disfluencies(ctx)
    changed = False
    for ev in doc.get("events") or []:
        if not isinstance(ev, dict):
            continue
        if ev.get("review_status") != "pending":
            continue
        ev["review_status"] = "confirmed"
        if ev.get("include_in_restore") is None:
            ev["include_in_restore"] = True
        changed = True
    if changed:
        recompute_stats(doc)
        ctx.write_json("transcript/disfluencies.json", doc)


def mark_disfluency_review_complete(ctx: RunContext, *, accept_unreviewed: bool = False) -> None:
    if accept_unreviewed:
        confirm_all_pending(ctx)
    doc = load_disfluencies(ctx)
    events = [e for e in (doc.get("events") or []) if isinstance(e, dict)]
    pending = [e for e in events if e.get("review_status") == "pending"]
    if pending:
        raise ValueError(f"{len(pending)} event(s) still pending review")

    summary = {
        "schema_version": 1,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "stats": doc.get("stats") or {},
        "confirmed_event_ids": [
            str(e.get("event_id")) for e in events if e.get("review_status") == "confirmed"
        ],
    }
    ctx.write_json("transcript/disfluency_review.json", summary)
    ctx.mark_done("disfluency_review")
    ctx.log("Disfluency review complete.", level="success", stage="disfluency_review")


def auto_complete_empty_review(ctx: RunContext) -> None:
    doc = load_disfluencies(ctx)
    if doc.get("events"):
        return
    if ctx.is_done("disfluency_review"):
        return
    mark_disfluency_review_complete(ctx)
