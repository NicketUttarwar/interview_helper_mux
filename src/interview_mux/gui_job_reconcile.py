from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.process_cleanup import worker_pid_alive
from interview_mux.run_context import RunContext
from interview_mux.session_log import append_log

RUNNING_STATUSES = frozenset({"running", "running_with_warnings"})
INTERRUPTED_MESSAGE = "Server restarted — safe to re-run."
STALLED_MESSAGE = "Stage stalled — no progress recently. Safe to re-run."
WRITE_APPROVAL_EXIT = 2


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def _stall_threshold_sec(*, job: dict[str, Any] | None = None) -> int:
    from interview_mux.config import merged_config

    row = merged_config().get("gui_job") or {}
    if job and job.get("worker_kind") == "stage_subprocess":
        return int(row.get("subprocess_stall_threshold_sec", 7200))
    return int(row.get("stall_threshold_sec", 180))


def _run_directory_lock_held(run_dir: Any) -> bool:
    from filelock import FileLock, Timeout

    lock_path = run_dir / ".run.lock"
    if not lock_path.is_file():
        return False
    lock = FileLock(str(lock_path), timeout=0)
    try:
        if lock.acquire(blocking=False):
            lock.release()
            return False
    except Timeout:
        return True
    return True


def _latest_log_ts(run_dir: Any) -> datetime | None:
    log_path = run_dir / "gui_log.jsonl"
    if not log_path.is_file():
        return None
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            import json

            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_ts(row.get("ts"))
        if ts is not None:
            return ts
    return None


def _job_activity_ts(ctx: RunContext, job: dict[str, Any]) -> datetime | None:
    updated = _parse_ts(job.get("updated_at"))
    logged = _latest_log_ts(ctx.run_dir)
    if updated and logged:
        if logged.tzinfo is None:
            logged = logged.replace(tzinfo=timezone.utc)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return max(updated, logged)
    return updated or logged


def _live_worker(job: dict[str, Any]) -> bool:
    """True when a tracked stage subprocess is still running."""
    if worker_pid_alive(job.get("worker_pid")):
        return True
    return False


def _revive_running_job(ctx: RunContext, job: dict[str, Any]) -> dict[str, Any]:
    """Clear false stall/interrupted state when a live worker is still executing."""
    out = dict(job)
    out["status"] = "running"
    out.pop("stalled", None)
    stage = out.get("current_stage") or out.get("stage") or "gui"
    msg = str(out.get("message") or "")
    if msg in {STALLED_MESSAGE, INTERRUPTED_MESSAGE} or not msg.strip():
        out["message"] = f"Running {stage}…"
    ctx.write_json("gui_job.json", out)
    return out


def _mark_stalled(ctx: RunContext, job: dict[str, Any]) -> dict[str, Any]:
    out = dict(job)
    out["status"] = "stalled"
    out["stalled"] = True
    out["message"] = STALLED_MESSAGE
    ctx.write_json("gui_job.json", out)
    append_log(
        ctx.run_dir,
        STALLED_MESSAGE,
        level="warning",
        stage=str(job.get("stage") or job.get("current_stage") or "gui"),
    )
    return out


def reconcile_operator_gate_job(ctx: RunContext, job: dict[str, Any]) -> dict[str, Any]:
    """Clear stale operator checkpoint gates once the checkpoint has been satisfied."""
    if str(job.get("status")) != "gate":
        return job
    stage = str(job.get("stage") or "")
    msg = str(job.get("message") or job.get("error") or "")
    low = msg.lower()

    from interview_mux.gate_focus import operator_gate_focus_stage

    focus = operator_gate_focus_stage(msg, job_stage=stage) or stage

    if focus == "transcript_review":
        from interview_mux.stages.transcript_review import check_transcript_review_pending

        if check_transcript_review_pending(ctx):
            return job
        return _resume_after_operator_gate(ctx, job, stage_id=stage, message="Transcript review complete — continue pipeline.")

    if focus == "disfluency_review":
        from interview_mux.gates import check_disfluency_review_pending

        if check_disfluency_review_pending(ctx):
            return job
        return _resume_after_operator_gate(ctx, job, stage_id=stage, message="Disfluency review complete — continue pipeline.")

    if stage == "transcript_review_build" and "transcript review required" in low:
        from interview_mux.stages.transcript_review import check_transcript_review_pending

        if not check_transcript_review_pending(ctx):
            return _resume_after_operator_gate(
                ctx,
                job,
                stage_id=stage,
                message="Transcript review complete — continue pipeline.",
            )

    return job


def _resume_after_operator_gate(
    ctx: RunContext,
    job: dict[str, Any],
    *,
    stage_id: str,
    message: str,
) -> dict[str, Any]:
    from interview_mux.write_staging import list_pending_paths

    paths = list_pending_paths(ctx, stage_id)
    if paths:
        out = dict(job)
        out["status"] = "awaiting_write_approval"
        out["mode"] = "stage"
        out["stage"] = stage_id
        out["current_stage"] = stage_id
        out["message"] = "Awaiting your review"
        out["pending_write_stage"] = stage_id
        out["pending_write_paths"] = paths
        out["awaiting_write_approval"] = True
        out.pop("error", None)
        return out

    if stage_id and not ctx.is_done(stage_id):
        ctx.mark_done(stage_id)

    out = dict(job)
    out["status"] = "complete"
    out["stage"] = stage_id
    out["current_stage"] = None
    out["message"] = message
    out.pop("error", None)
    return out


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


def _reconcile_job_file(ctx: RunContext, *, lock_held: bool) -> bool:
    """Rewrite stale on-disk running job to interrupted. Returns True if changed."""
    p = ctx.path("gui_job.json")
    if not p.is_file():
        return False
    data = ctx.read_json("gui_job.json")
    status = data.get("status")
    if status not in RUNNING_STATUSES:
        return False
    if not lock_held and _run_directory_lock_held(ctx.run_dir):
        return False
    if lock_held:
        if _live_worker(data):
            return False
        activity = _job_activity_ts(ctx, data)
        if activity is not None:
            now = datetime.now(timezone.utc)
            if activity.tzinfo is None:
                activity = activity.replace(tzinfo=timezone.utc)
            age = (now - activity).total_seconds()
            if age >= _stall_threshold_sec(job=data):
                _mark_stalled(ctx, data)
                return True
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
    return _reconcile_job_file(ctx, lock_held=False)


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
    data = ctx.read_json("gui_job.json")
    status = data.get("status")
    if status in RUNNING_STATUSES:
        _reconcile_job_file(ctx, lock_held=lock_held)
        data = ctx.read_json("gui_job.json")
    elif status in {"stalled", "interrupted"} and _live_worker(data):
        data = _revive_running_job(ctx, data)
    sanitized = sanitize_gui_job(ctx, data)
    if sanitized is not data and sanitized != data:
        ctx.write_json("gui_job.json", sanitized)
        data = sanitized
    reconciled = reconcile_operator_gate_job(ctx, data)
    if reconciled is not data:
        ctx.write_json("gui_job.json", reconciled)
        data = reconciled
    data["run_id"] = run_id
    return data


def pause_job_for_write_approval(ctx: RunContext, exc: Any) -> None:
    """Persist awaiting_write_approval gui_job from an isolated stage worker."""
    from interview_mux.write_staging import WriteApprovalPending

    if not isinstance(exc, WriteApprovalPending):
        raise TypeError("expected WriteApprovalPending")
    ctx.write_json(
        "gui_job.json",
        {
            "status": "awaiting_write_approval",
            "mode": "stage",
            "stage": exc.stage_id,
            "current_stage": exc.stage_id,
            "message": str(exc),
            "pending_write_stage": exc.stage_id,
            "pending_write_paths": exc.paths,
            "awaiting_write_approval": True,
        },
    )
