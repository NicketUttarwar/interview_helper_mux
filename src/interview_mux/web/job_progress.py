"""Live gui_job.json updates during multi-stage batch and Homunculus walks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

_StageHook = Callable[[str, int, int, list[str]], None]
_UNSET = object()
_RUNNING = frozenset({"running", "running_with_warnings", "stalled"})

_hooks: dict[str, _StageHook] = {}
_job_bases: dict[str, dict[str, Any]] = {}


def register_job_progress(
    run_id: str,
    hook: _StageHook,
    *,
    job_base: dict[str, Any] | None = None,
) -> None:
    _hooks[run_id] = hook
    if job_base is not None:
        _job_bases[run_id] = job_base


def clear_job_progress(run_id: str) -> None:
    _hooks.pop(run_id, None)
    _job_bases.pop(run_id, None)


def _stage_title(stage_id: str) -> str:
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID.get(stage_id)
    return info.title if info else stage_id.replace("_", " ")


def _infer_parent_stage(ctx: Any, stage_id: str) -> str | None:
    if getattr(ctx, "_chapter_close_hitch_inner", False) and stage_id != "chapter_close_hitch":
        return "chapter_close_hitch"
    return None


def persist_running_stage_progress(
    run_id: str,
    stage_id: str,
    *,
    index: int = 0,
    total: int = 0,
    stages_planned: list[str] | None = None,
    parent_stage: Any = _UNSET,
    job_base: dict[str, Any] | None = None,
    message: str | None = None,
    mark_previous_done: bool = True,
    ctx: Any = None,
) -> dict[str, Any] | None:
    """Merge the executing stage into gui_job.json without clobbering the batch plan."""
    from interview_mux.run_context import RunContext

    if ctx is None:
        if not RunContext.exists(run_id):
            return None
        ctx = RunContext(run_id, create=False)
    job: dict[str, Any] = {}
    if ctx.artifact_exists("gui_job.json"):
        try:
            loaded = ctx.read_json("gui_job.json")
        except OSError:
            loaded = None
        if isinstance(loaded, dict):
            job = loaded

    base = job_base or _job_bases.get(run_id) or {}
    status = str(job.get("status") or "")
    if status not in _RUNNING:
        if not base:
            return None
        job = {**base, **job}
        job["status"] = "running"

    caller_planned = [str(s) for s in (stages_planned or []) if s]
    existing_planned = [
        str(s)
        for s in (job.get("stages_planned") or base.get("stages_planned") or [])
        if s
    ]
    inherit_batch = total <= 1 and len(caller_planned) <= 1 and (
        len(existing_planned) > 1 or int(job.get("stage_total") or base.get("stage_total") or 0) > 1
    )
    planned = existing_planned if inherit_batch else (caller_planned or existing_planned)
    existing_total = int(job.get("stage_total") or base.get("stage_total") or 0)
    if inherit_batch:
        total = max(len(planned), existing_total, 1)
        if stage_id in planned:
            index = planned.index(stage_id) + 1
        elif index <= 0:
            index = int(job.get("stage_index") or 1)
    else:
        if total <= 0:
            total = max(len(planned), existing_total, 1)
        if index <= 0:
            if stage_id in planned:
                index = planned.index(stage_id) + 1
            else:
                index = max(int(job.get("stage_index") or 0), 1)

    done = [str(s) for s in (job.get("stages_done") or []) if s]
    prev = str(job.get("current_stage") or "")
    if not prev:
        prev = str(job.get("stage") or "")
    stage_changed = bool(prev) and prev != stage_id
    inferred_parent = _infer_parent_stage(ctx, stage_id)
    if mark_previous_done and stage_changed and prev not in done:
        live_parent = inferred_parent or job.get("parent_stage")
        if prev != live_parent and (not planned or prev in planned):
            done.append(prev)

    out = dict(job)
    for key, value in base.items():
        if key not in {
            "status",
            "stage",
            "current_stage",
            "message",
            "stage_index",
            "stage_total",
            "stages_planned",
            "stages_done",
            "parent_stage",
            "error",
            "traceback",
            "last_error",
            "stalled",
        }:
            out.setdefault(key, value)

    live_status = str(out.get("status") or "running")
    if live_status == "stalled":
        live_status = "running"
        out.pop("stalled", None)
    elif live_status not in _RUNNING:
        live_status = "running"
    out["status"] = live_status
    out["stage"] = stage_id
    out["current_stage"] = stage_id
    out["stage_index"] = int(index)
    out["stage_total"] = int(total)
    if planned:
        out["stages_planned"] = planned
    out["stages_done"] = done
    if parent_stage is _UNSET:
        if inferred_parent:
            out["parent_stage"] = inferred_parent
        elif inferred_parent is None and not getattr(ctx, "_chapter_close_hitch_inner", False):
            out.pop("parent_stage", None)
    elif parent_stage:
        out["parent_stage"] = str(parent_stage)
    else:
        out.pop("parent_stage", None)
    title = _stage_title(stage_id)
    parent = out.get("parent_stage")
    if message:
        out["message"] = message
    elif parent and parent != stage_id:
        out["message"] = (
            f"Running {_stage_title(str(parent))} → {title}… ({index}/{total})"
        )
    else:
        out["message"] = f"Running {title}… ({index}/{total})"
    if stage_changed:
        out.pop("phase", None)
        out.pop("step_index", None)
        out.pop("step_total", None)
    out["updated_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json("gui_job.json", out)
    return out


def notify_batch_plan(
    run_id: str,
    stages_planned: list[str],
    *,
    message: str | None = None,
) -> dict[str, Any] | None:
    """Record the remaining batch without pretending a stage is executing yet."""
    from interview_mux.run_context import RunContext

    planned = [str(s) for s in stages_planned if s]
    if not planned or not RunContext.exists(run_id):
        return None
    ctx = RunContext(run_id, create=False)
    if not ctx.artifact_exists("gui_job.json"):
        return None
    try:
        job = ctx.read_json("gui_job.json")
    except OSError:
        return None
    if not isinstance(job, dict) or str(job.get("status") or "") not in _RUNNING:
        return None
    out = dict(job)
    out["stages_planned"] = planned
    out["stage_total"] = len(planned)
    idx = out.get("stage_index")
    current = str(out.get("current_stage") or out.get("stage") or "")
    if current and current in planned:
        out["stage_index"] = planned.index(current) + 1
    elif not idx:
        out["stage_index"] = 0
    if message:
        out["message"] = message
    out["updated_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json("gui_job.json", out)
    return out


_GATE_STATUS_STAGES = frozenset(
    {
        "transcript_review",
        "missing_framing",
        "analysis_profile",
        "g1_vo_pickup",
        "g1_5_preview_pickup",
    }
)


def overlay_stage_list_status(
    ctx: Any,
    stages: list[dict[str, Any]],
    job: dict[str, Any] | None = None,
) -> None:
    """Align GUI stage pills with live job identity and seated outputs."""
    running_ids: set[str] = set()
    if job and str(job.get("status") or "") in _RUNNING:
        for key in ("current_stage", "parent_stage"):
            val = job.get(key)
            if val:
                running_ids.add(str(val))
        for row in job.get("stage_progress") or []:
            if isinstance(row, dict) and row.get("status") == "running" and row.get("id"):
                running_ids.add(str(row["id"]))
    check_outputs: set[str] = set()
    if job:
        check_outputs.update(str(s) for s in (job.get("stages_planned") or []) if s)
        check_outputs.update(str(s) for s in (job.get("stages_done") or []) if s)
    if not running_ids and not check_outputs:
        return
    try:
        from interview_mux.homunculus.agenda import stage_outputs_present
    except Exception:
        stage_outputs_present = None  # type: ignore[assignment]

    for stage in stages:
        sid = str(stage.get("id") or "")
        if not sid or sid in _GATE_STATUS_STAGES:
            continue
        status = stage.get("status")
        if sid in running_ids:
            if status in ("done", "locked"):
                stage["status"] = "pending"
            continue
        if sid not in check_outputs:
            continue
        if status not in ("pending", "done", "incomplete"):
            continue
        if stage.get("stage_output_mode") in ("optional_skipped", "n_a"):
            continue
        if stage_outputs_present is None:
            continue
        try:
            present = bool(stage_outputs_present(ctx, sid))
        except Exception:
            continue
        if present and status == "pending":
            arts = stage.get("artifacts_status") or {}
            lifecycle = stage.get("artifacts_lifecycle") or {}
            if any(
                st in ("pending", "partial")
                and lifecycle.get(path) not in ("n_a", "skipped")
                for path, st in arts.items()
            ):
                continue
            stage["status"] = "done"
            stage.pop("incomplete_reason", None)


def attach_live_stage_progress(run_id: str, job: dict[str, Any]) -> dict[str, Any]:
    """Derived per-stage status for GET /job so the GUI can refresh without GET /runs."""
    if not isinstance(job, dict):
        return job
    planned = [str(s) for s in (job.get("stages_planned") or []) if s]
    if not planned:
        return job
    from interview_mux.run_context import RunContext

    if not RunContext.exists(run_id):
        return job
    ctx = RunContext(run_id, create=False)
    done_set = {str(s) for s in (job.get("stages_done") or []) if s}
    current = str(job.get("current_stage") or "")
    parent = str(job.get("parent_stage") or "")
    running = str(job.get("status") or "") in _RUNNING
    progress: list[dict[str, str]] = []
    for sid in planned:
        if running and sid in {current, parent}:
            status = "running"
        elif sid in done_set or ctx.is_done(sid):
            status = "done"
        else:
            status = "pending"
        progress.append({"id": sid, "status": status})
    out = dict(job)
    out["stage_progress"] = progress
    return out


def notify_stage_start(
    run_id: str,
    stage_id: str,
    *,
    index: int,
    total: int,
    stages_planned: list[str],
    parent_stage: Any = _UNSET,
    message: str | None = None,
    ctx: Any = None,
) -> None:
    persist_running_stage_progress(
        run_id,
        stage_id,
        index=index,
        total=total,
        stages_planned=stages_planned,
        parent_stage=parent_stage,
        message=message,
        ctx=ctx,
    )
    hook = _hooks.get(run_id)
    if hook is not None:
        hook(stage_id, index, total, stages_planned)
