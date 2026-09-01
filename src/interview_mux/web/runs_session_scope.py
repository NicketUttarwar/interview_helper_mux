"""Session-scoped execution listing — active run + immediate previous only."""

from __future__ import annotations

from typing import Any

from interview_mux.application_session import active_run_id
from interview_mux.run_context import RunContext
from interview_mux.session_lineage import resolve_immediate_previous_run_id


def session_scoped_run_ids() -> list[str]:
    """Return 0–2 run ids: active session run and its immediate previous (deduped)."""
    active = active_run_id()
    if not active or not RunContext.exists(active):
        return []
    ids: list[str] = [active]
    try:
        ctx = RunContext(active, create=False)
        prev = resolve_immediate_previous_run_id(ctx)
        if prev and prev != active and RunContext.exists(prev):
            ids.append(prev)
    except OSError:
        pass
    return ids


def enrich_run_summary(
    run_id: str,
    *,
    summarize_fn: Any,
    build_stage_list_fn: Any,
    build_journey_fn: Any,
    get_job_fn: Any,
    read_log_fn: Any,
    check_g1_vo: Any,
    check_transcript_review_pending: Any,
    is_operator_profile_verified: Any,
    check_profile_gate_pending: Any,
) -> dict[str, Any]:
    """Lightweight summary + journey fields for one run."""
    try:
        r = dict(summarize_fn(run_id))
        ctx = RunContext(run_id, create=False)
        job = get_job_fn(run_id)
        stages = build_stage_list_fn(
            ctx,
            check_g1_vo(ctx),
            check_transcript_review_pending(ctx),
            is_operator_profile_verified(ctx),
            check_profile_gate_pending(ctx),
            job=job,
        )
        done = sum(1 for s in stages if s["status"] == "done")
        r["progress"] = {"done": done, "total": len(stages)}
        r["last_stage"] = next(
            (s["title"] for s in reversed(stages) if s["status"] == "done"),
            None,
        )
        log_entries = read_log_fn(ctx.run_dir, tail=1)
        if log_entries:
            r["last_log"] = log_entries[-1]
        if job.get("status"):
            r["job_status"] = job.get("status")
        journey = build_journey_fn(ctx, job=job, stages=stages)
        r["operator_phase"] = journey.get("phase")
        next_action = str(journey.get("next_action") or "")
        r["next_action"] = next_action[:80] if next_action else None
        blocking = journey.get("blocking") or {}
        r["blocking_message"] = blocking.get("message") if blocking.get("blocked") else None
        attention = sum(1 for s in stages if s.get("status") == "action_required")
        if job.get("status") in ("gate", "needs_operator") or job.get("needs_stage_reuse"):
            attention += 1
        if blocking.get("blocked"):
            attention = max(attention, 1)
        r["attention_count"] = attention
        return r
    except Exception:
        return {"run_id": run_id, "progress": {"done": 0, "total": 0}}


def build_session_scope_payload(
    *,
    summarize_fn: Any,
    enrich_fn: Any,
) -> dict[str, Any]:
    ids = session_scoped_run_ids()
    active = ids[0] if ids else None
    previous = ids[1] if len(ids) > 1 else None
    runs = [enrich_fn(rid) for rid in ids]
    runs.sort(key=lambda r: r.get("execution_number") or 0, reverse=True)
    return {
        "active_run_id": active,
        "immediate_previous_run_id": previous,
        "runs": runs,
    }
