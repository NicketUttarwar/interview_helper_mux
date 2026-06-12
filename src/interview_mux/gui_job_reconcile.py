from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.session_log import append_log

RUNNING_STATUSES = frozenset({"running", "running_with_warnings"})
INTERRUPTED_MESSAGE = "Server restarted — safe to re-run."


def _reconcile_job_file(ctx: RunContext) -> bool:
    """Rewrite stale on-disk running job to interrupted. Returns True if changed."""
    p = ctx.path("gui_job.json")
    if not p.is_file():
        return False
    data = ctx.read_json("gui_job.json")
    status = data.get("status")
    if status not in RUNNING_STATUSES:
        return False
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
    data["run_id"] = run_id
    return data
