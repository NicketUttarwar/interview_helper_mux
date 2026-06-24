from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.session_log import append_log

RUNNING_STATUSES = frozenset({"running", "running_with_warnings"})
INTERRUPTED_MESSAGE = "Server restarted — safe to re-run."


def sanitize_gui_job(ctx: RunContext, job: dict[str, Any]) -> dict[str, Any]:
    """Drop stale reuse pause flags and backfill candidates from run_meta / disk."""
    if not job:
        return job
    stage = job.get("pending_write_stage") or job.get("stage")
    if not job.get("needs_stage_reuse") or not stage:
        return job

    from interview_mux.stage_execution_reuse import (
        get_reuse_decision,
        reuse_candidates_if_undecided,
    )

    stage_id = str(stage)
    decision = get_reuse_decision(ctx, stage_id)
    if decision:
        out = dict(job)
        out["needs_stage_reuse"] = False
        out.pop("reuse_candidates", None)
        if out.get("status") == "needs_operator":
            out["status"] = "complete"
            out["message"] = "Reuse decision recorded — continue when ready."
        return out

    candidates = job.get("reuse_candidates")
    if not candidates:
        found = reuse_candidates_if_undecided(ctx, stage_id)
        if found:
            out = dict(job)
            out["reuse_candidates"] = [c.to_dict() for c in found]
            return out
        if job.get("status") == "needs_operator":
            out = dict(job)
            out["needs_stage_reuse"] = False
            out["status"] = "idle"
            out["message"] = "Reuse no longer available — run this step fresh."
            return out
    return job


def _reconcile_job_file(ctx: RunContext) -> bool:
    """Rewrite stale on-disk running job to interrupted. Returns True if changed."""
    p = ctx.path("gui_job.json")
    if not p.is_file():
        return False
    data = ctx.read_json("gui_job.json")
    status = data.get("status")
    if status not in RUNNING_STATUSES:
        return False
    if data.get("mode") == "write_approval":
        from interview_mux.write_staging import list_pending_paths

        stage_id = str(data.get("pending_write_stage") or data.get("stage") or "")
        paths = list_pending_paths(ctx, stage_id) if stage_id else []
        if not paths:
            meta_paths = data.get("pending_write_paths") or []
            if isinstance(meta_paths, list):
                paths = [str(p) for p in meta_paths]
        if stage_id and paths:
            data["status"] = "awaiting_write_approval"
            data["mode"] = "stage"
            data["stage"] = stage_id
            data["current_stage"] = stage_id
            data["message"] = "Awaiting your review"
            data["pending_write_stage"] = stage_id
            data["pending_write_paths"] = paths
            data["awaiting_write_approval"] = True
            ctx.write_json("gui_job.json", data)
            append_log(
                ctx.run_dir,
                "Staged save interrupted — review outputs and save again.",
                level="warning",
                stage=stage_id,
            )
            return True
    data["status"] = "interrupted"
    data["message"] = INTERRUPTED_MESSAGE
    ctx.write_json("gui_job.json", data)
    append_log(
        ctx.run_dir,
        INTERRUPTED_MESSAGE,
        level="warning",
        stage=data.get("stage") or "gui",
    )
    return True


def reconcile_stale_job(run_id: str) -> bool:
    """Reconcile one run when gui_job.json claims running but no live worker."""
    if not RunContext.exists(run_id):
        return False
    ctx = RunContext(run_id, create=False)
    return _reconcile_job_file(ctx)


def reconcile_stale_jobs() -> int:
    """Scan all executions and interrupt stale running gui_job.json files."""
    count = 0
    for run_id in RunContext.list_runs():
        try:
            if reconcile_stale_job(run_id):
                count += 1
        except OSError:
            continue
    return count


def reconcile_job_if_stale(run_id: str, *, lock_held: bool) -> dict[str, Any]:
    """Return gui_job payload, reconciling disk when not lock_held but status is running."""
    ctx = RunContext(run_id, create=False)
    p = ctx.path("gui_job.json")
    if not p.is_file():
        return {"status": "idle", "run_id": run_id}
    if not lock_held:
        status = ctx.read_json("gui_job.json").get("status")
        if status in RUNNING_STATUSES:
            _reconcile_job_file(ctx)
    data = ctx.read_json("gui_job.json")
    sanitized = sanitize_gui_job(ctx, data)
    if sanitized is not data and sanitized != data:
        ctx.write_json("gui_job.json", sanitized)
        data = sanitized
    data["run_id"] = run_id
    return data
