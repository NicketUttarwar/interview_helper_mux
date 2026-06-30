"""Per-stage write staging — outputs land in .pending_writes/ until operator approves."""

from __future__ import annotations

import shutil
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

from interview_mux.config import merged_config
from interview_mux.file_store import lock_path_for
from interview_mux.file_store import read_json as fs_read_json
from interview_mux.file_store import read_text as fs_read_text
from interview_mux.file_store import write_json as fs_write_json
from interview_mux.file_store import write_text as fs_write_text
from interview_mux.run_context import RunContext

_active_stage: ContextVar[str | None] = ContextVar("write_staging_stage", default=None)

OPERATIONAL_REL_PATHS = frozenset(
    {
        "run_meta.json",
        "gui_job.json",
        "gui_log.jsonl",
    }
)


def write_approval_enabled() -> bool:
    cfg = merged_config().get("journey_ui") or {}
    if not isinstance(cfg, dict):
        return True
    return bool(cfg.get("require_write_approval_per_stage", True))


def enter_stage_staging(stage_id: str) -> None:
    _active_stage.set(stage_id)


def exit_stage_staging() -> None:
    _active_stage.set(None)


def is_operational_path(rel: str) -> bool:
    if rel in OPERATIONAL_REL_PATHS:
        return True
    if rel.startswith(".stage_done/"):
        return True
    return False


def staging_root(ctx: RunContext, stage_id: str) -> Path:
    return ctx.run_dir / ".pending_writes" / stage_id


def staged_path(ctx: RunContext, rel: str, *, stage_id: str | None = None) -> Path:
    sid = stage_id or _active_stage.get()
    if not sid:
        return ctx.run_dir.joinpath(*rel.split("/"))
    return staging_root(ctx, sid).joinpath(*rel.split("/"))


def resolve_write_path(ctx: RunContext, rel: str) -> Path:
    """Return staging path when approval enabled and stage active; else final path."""
    if not write_approval_enabled():
        return ctx.run_dir.joinpath(*rel.split("/"))
    sid = _active_stage.get()
    if not sid or is_operational_path(rel):
        return ctx.run_dir.joinpath(*rel.split("/"))
    return staged_path(ctx, rel, stage_id=sid)


def staging_approval_hint(ctx: RunContext, rel: str) -> str | None:
    """If rel exists only in unapproved staging, return an operator remediation hint."""
    if is_operational_path(rel):
        return None
    if ctx.run_dir.joinpath(*rel.split("/")).is_file():
        return None
    pending_root = ctx.run_dir / ".pending_writes"
    if not pending_root.is_dir():
        return None
    for stage_dir in sorted(pending_root.iterdir()):
        if not stage_dir.is_dir():
            continue
        candidate = stage_dir.joinpath(*rel.split("/"))
        if candidate.is_file():
            return (
                f"{rel} is awaiting write approval for stage '{stage_dir.name}' — "
                "open the review modal and choose Save & continue before running later stages."
            )
    return None


def staging_read_trap_hint(ctx: RunContext, rel: str) -> str | None:
    """Hint when an approved artifact exists but the active staging write root would miss it."""
    if is_operational_path(rel):
        return None
    resolved = resolve_read_path(ctx, rel)
    if not resolved.is_file():
        return staging_approval_hint(ctx, rel)
    staged = staged_path(ctx, rel)
    if staged == resolved or staged.is_file():
        return None
    return (
        f"{rel} exists at {resolved} but not under the active staging directory ({staged}). "
        "Prior-stage inputs must be read via read_path(), not path()."
    )


def resolve_read_path(ctx: RunContext, rel: str) -> Path:
    """Prefer staged copy when present."""
    if is_operational_path(rel):
        return ctx.run_dir.joinpath(*rel.split("/"))
    sid = _active_stage.get()
    if sid:
        staged = staged_path(ctx, rel, stage_id=sid)
        if staged.is_file():
            return staged
    pending = pending_stage_for_path(ctx, rel)
    if pending:
        staged = staged_path(ctx, rel, stage_id=pending)
        if staged.is_file():
            return staged
    return ctx.run_dir.joinpath(*rel.split("/"))


def artifact_exists_resolved(ctx: RunContext, rel: str) -> bool:
    if is_operational_path(rel):
        return ctx.run_dir.joinpath(*rel.split("/")).is_file()
    p = resolve_read_path(ctx, rel)
    return p.is_file()


def list_pending_paths(ctx: RunContext, stage_id: str) -> list[str]:
    root = staging_root(ctx, stage_id)
    if not root.is_dir():
        return []
    paths: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != ".write.lock":
            paths.append(str(p.relative_to(root)).replace("\\", "/"))
    return paths


def pending_stage_for_path(ctx: RunContext, rel: str) -> str | None:
    if is_operational_path(rel):
        return None
    meta_path = ctx.run_dir / "run_meta.json"
    if not meta_path.is_file():
        return None
    meta = ctx.read_json("run_meta.json")
    if not isinstance(meta, dict):
        return None
    pending = meta.get("pending_write_approval") or {}
    if not isinstance(pending, dict):
        return None
    for sid, info in pending.items():
        paths = info.get("paths") if isinstance(info, dict) else None
        if isinstance(paths, list) and rel in paths:
            return str(sid)
    base = staging_root(ctx, "")
    if not (ctx.run_dir / ".pending_writes").is_dir():
        return None
    for stage_dir in sorted((ctx.run_dir / ".pending_writes").iterdir()):
        if not stage_dir.is_dir():
            continue
        candidate = stage_dir.joinpath(*rel.split("/"))
        if candidate.is_file():
            return stage_dir.name
    return None


def has_pending_writes(ctx: RunContext, stage_id: str) -> bool:
    return bool(list_pending_paths(ctx, stage_id))


def record_pending_approval(ctx: RunContext, stage_id: str) -> None:
    paths = list_pending_paths(ctx, stage_id)
    if not paths:
        return
    created = datetime.now(timezone.utc).isoformat()

    def _patch(meta: dict[str, Any]) -> None:
        pending = dict(meta.get("pending_write_approval") or {})
        pending[stage_id] = {"paths": paths, "created_at": created}
        meta["pending_write_approval"] = pending

    ctx.mutate_run_meta(_patch)


def clear_pending_approval(ctx: RunContext, stage_id: str) -> None:
    if not ctx.final_path("run_meta.json").is_file():
        return

    def _patch(meta: dict[str, Any]) -> None:
        pending = dict(meta.get("pending_write_approval") or {})
        pending.pop(stage_id, None)
        meta["pending_write_approval"] = pending

    ctx.mutate_run_meta(_patch)


def _staging_lock(ctx: RunContext, stage_id: str) -> FileLock:
    root = staging_root(ctx, stage_id)
    root.mkdir(parents=True, exist_ok=True)
    return FileLock(lock_path_for(root / ".staging.lock"))


_LARGE_FLUSH_BYTES = 8 << 20  # 8 MiB


def flush_stage_writes(ctx: RunContext, stage_id: str) -> list[str]:
    with _staging_lock(ctx, stage_id):
        root = staging_root(ctx, stage_id)
        if not root.is_dir():
            clear_pending_approval(ctx, stage_id)
            return []
        flushed: list[str] = []
        from interview_mux.file_store import atomic_copy
        from interview_mux.operator_subprocess import touch_job_message

        for src in sorted(root.rglob("*")):
            if not src.is_file() or src.name.endswith(".lock"):
                continue
            rel = str(src.relative_to(root)).replace("\\", "/")
            dest = ctx.run_dir.joinpath(*rel.split("/"))
            size = src.stat().st_size
            if size >= _LARGE_FLUSH_BYTES:
                mb = size / (1 << 20)
                msg = f"Promoting {rel} ({mb:.1f} MiB) to working directory…"
                touch_job_message(ctx, msg)
                ctx.log(
                    msg,
                    level="info",
                    stage=stage_id,
                    action_id="write_approval.flush",
                    origin="api",
                    detail={
                        "journey_kind": "execute",
                        "event": "flush_progress",
                        "path": rel,
                        "bytes": size,
                    },
                )

                def _progress(copied: int, total: int, *, _rel: str = rel) -> None:
                    if total and copied >= total:
                        ctx.log(
                            f"Promoted {_rel}",
                            level="info",
                            stage=stage_id,
                            action_id="write_approval.flush",
                            origin="api",
                        )

                atomic_copy(src, dest, on_progress=_progress if size >= _LARGE_FLUSH_BYTES else None)
            else:
                atomic_copy(src, dest)
            flushed.append(rel)
        shutil.rmtree(root, ignore_errors=True)
    clear_pending_approval(ctx, stage_id)
    return flushed


def discard_stage_writes(ctx: RunContext, stage_id: str) -> None:
    with _staging_lock(ctx, stage_id):
        root = staging_root(ctx, stage_id)
        if root.is_dir():
            shutil.rmtree(root, ignore_errors=True)
    clear_pending_approval(ctx, stage_id)
    from interview_mux.attempt_budget import reset_stage_attempt_budget

    reset_stage_attempt_budget(ctx, stage_id)


def read_pending_content(ctx: RunContext, stage_id: str, rel: str) -> bytes:
    p = staged_path(ctx, rel, stage_id=stage_id)
    if not p.is_file():
        raise FileNotFoundError(rel)
    return p.read_bytes()


def write_pending_content(
    ctx: RunContext,
    stage_id: str,
    rel: str,
    *,
    data: dict[str, Any] | None = None,
    text: str | None = None,
    raw: bytes | None = None,
) -> Path:
    p = staged_path(ctx, rel, stage_id=stage_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    if data is not None:
        fs_write_json(p, data)
    elif text is not None:
        fs_write_text(p, text)
    elif raw is not None:
        p.write_bytes(raw)
    else:
        raise ValueError("Provide data, text, or raw")
    record_pending_approval(ctx, stage_id)
    return p


def all_pending_stages(ctx: RunContext) -> list[str]:
    meta_path = ctx.run_dir / "run_meta.json"
    if not meta_path.is_file():
        return []
    meta = ctx.read_json("run_meta.json")
    pending = meta.get("pending_write_approval") if isinstance(meta, dict) else {}
    if isinstance(pending, dict) and pending:
        return list(pending.keys())
    root = ctx.run_dir / ".pending_writes"
    if not root.is_dir():
        return []
    return [p.name for p in sorted(root.iterdir()) if p.is_dir() and list_pending_paths(ctx, p.name)]


def read_pending_json(ctx: RunContext, stage_id: str, rel: str) -> Any:
    return fs_read_json(staged_path(ctx, rel, stage_id=stage_id))


def read_pending_text(ctx: RunContext, stage_id: str, rel: str) -> str:
    return fs_read_text(staged_path(ctx, rel, stage_id=stage_id))


class WriteApprovalBlockedError(Exception):
    """Staged save blocked — stage failed an operator or LLM gate."""

    def __init__(self, stage_id: str, message: str) -> None:
        self.stage_id = stage_id
        super().__init__(message)


class WriteApprovalPending(Exception):
    """Pipeline paused until operator approves staged writes."""

    def __init__(self, stage_id: str, paths: list[str]) -> None:
        self.stage_id = stage_id
        self.paths = paths
        super().__init__(
            f"Stage '{stage_id}' outputs await review before saving ({len(paths)} file(s))."
        )


def read_gui_job(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("gui_job.json"):
        return None
    try:
        job = ctx.read_json("gui_job.json")
    except Exception:
        return None
    return job if isinstance(job, dict) else None


def set_llm_gate(ctx: RunContext, stage_id: str, *, message: str) -> None:
    """Record an unrecoverable LLM gate on gui_job (GUI runner / write-approval flows)."""
    job = read_gui_job(ctx) or {}
    if not isinstance(job, dict):
        job = {}
    job["status"] = "gate"
    job["stage"] = stage_id
    job["message"] = message
    ctx.write_json("gui_job.json", job, skip_handoff=True)


def gate_blocked_stage(ctx: RunContext) -> str | None:
    """Stage id when gui_job is paused on a gate for an incomplete stage."""
    job = read_gui_job(ctx)
    if not job or str(job.get("status")) != "gate":
        return None
    stage_id = str(job.get("stage") or "")
    if not stage_id or ctx.is_done(stage_id):
        return None
    return stage_id


def is_llm_gate_blocked(ctx: RunContext, stage_id: str) -> bool:
    return gate_blocked_stage(ctx) == stage_id


def is_itr_clarification_blocked(ctx: RunContext, stage_id: str) -> bool:
    job = read_gui_job(ctx) or {}
    if str(job.get("status")) != "needs_clarification":
        return False
    if str(job.get("stage") or "") != stage_id:
        return False
    from interview_mux.artifact_issue_triage import blocking_issues_remaining, triage_enabled

    return triage_enabled() and blocking_issues_remaining(ctx, stage_id) > 0


def is_stage_gate_blocked(ctx: RunContext, stage_id: str) -> bool:
    return is_llm_gate_blocked(ctx, stage_id) or is_itr_clarification_blocked(ctx, stage_id)


def write_approval_allowed(ctx: RunContext, stage_id: str) -> bool:
    """True when staged outputs may be saved for this stage."""
    if is_stage_gate_blocked(ctx, stage_id):
        return False
    if not write_approval_enabled():
        return True
    return has_pending_writes(ctx, stage_id)


def assert_write_approval_allowed(ctx: RunContext, stage_id: str) -> None:
    """Raise when operator save must not proceed for this stage."""
    if is_stage_gate_blocked(ctx, stage_id):
        job = read_gui_job(ctx) or {}
        if str(job.get("status")) == "needs_clarification":
            from interview_mux.artifact_issue_triage import assert_write_approval_itr_ok

            assert_write_approval_itr_ok(ctx, stage_id)
        msg = str(
            job.get("message")
            or (
                f"Stage {stage_id} failed the LLM quality gate — "
                "re-run or discard staged outputs instead of saving."
            )
        )
        raise WriteApprovalBlockedError(stage_id, msg)
    from interview_mux.artifact_issue_triage import assert_write_approval_itr_ok

    assert_write_approval_itr_ok(ctx, stage_id)
    if not has_pending_writes(ctx, stage_id):
        raise FileNotFoundError(f"No pending writes for stage: {stage_id}")


def after_stage_write_check(ctx: RunContext, stage_id: str) -> None:
    if write_approval_enabled() and has_pending_writes(ctx, stage_id):
        record_pending_approval(ctx, stage_id)
        raise WriteApprovalPending(stage_id, list_pending_paths(ctx, stage_id))


def run_wrapped_stage(ctx: RunContext, stage_id: str, fn: Any) -> None:
    """Execute a stage function with optional write staging."""
    from interview_mux.operator_trace import active_run_context, log_step

    ctx_token = active_run_context.set(ctx)
    try:
        log_step(f"Preparing stage: {stage_id}", ctx=ctx, stage=stage_id)
        from interview_mux.stage_input_checks import require_stage_inputs

        require_stage_inputs(ctx, stage_id)
        if write_approval_enabled():
            enter_stage_staging(stage_id)
        try:
            fn()
            ctx.log(
                f"Stage finished: {stage_id}",
                level="success",
                stage=stage_id,
                detail={"journey_kind": "execute", "event": "stage_finish"},
            )
        except WriteApprovalPending:
            raise
        except Exception as exc:
            from interview_mux.operator_trace import log_stage_error

            log_stage_error(stage_id, exc, ctx=ctx)
            raise
        finally:
            if write_approval_enabled():
                exit_stage_staging()
        after_stage_write_check(ctx, stage_id)
    finally:
        active_run_context.reset(ctx_token)


def check_write_approval_before_execute(ctx: RunContext) -> WriteApprovalPending | None:
    stages = all_pending_stages(ctx)
    if not stages:
        return None
    sid = stages[0]
    paths = list_pending_paths(ctx, sid)
    if not paths:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        pending = meta.get("pending_write_approval") if isinstance(meta, dict) else {}
        if isinstance(pending, dict) and sid in pending:
            paths = list(pending[sid].get("paths") or [])
    return WriteApprovalPending(sid, paths)


def approve_stage_writes(ctx: RunContext, stage_id: str) -> list[str]:
    from interview_mux.operator_action_trace import begin_action, end_action

    trace_id = begin_action(
        "write_approval.approve",
        run_dir=ctx.run_dir,
        stage=stage_id,
        origin="api",
        summary=f"Approve staged writes for {stage_id}",
        function="write_staging.approve_stage_writes",
    )
    try:
        flushed = flush_stage_writes(ctx, stage_id)
        if "segments/manifest.json" in flushed and ctx.artifact_exists("segments/manifest.json"):
            from interview_mux.artifact_completeness import hydrate_manifest_from_boundaries

            manifest = ctx.read_json("segments/manifest.json")
            hydrated = hydrate_manifest_from_boundaries(ctx, manifest)
            if hydrated != manifest:
                ctx.write_json("segments/manifest.json", hydrated, stage_key=stage_id)
        ctx.mark_done(stage_id, force=True)
        now = datetime.now(timezone.utc).isoformat()

        def _ack(meta: dict[str, Any]) -> None:
            ack = dict(meta.get("handoff_ack") or {})
            ack[stage_id] = now
            meta["handoff_ack"] = ack

        ctx.mutate_run_meta(_ack)
        if stage_id == "disfluency_extract":
            from interview_mux.stages.disfluency import maybe_auto_complete_review

            maybe_auto_complete_review(ctx)
        end_action(
            trace_id,
            run_dir=ctx.run_dir,
            status="ok",
            detail={"flushed": flushed, "stage_id": stage_id},
        )
        return flushed
    except Exception:
        end_action(trace_id, run_dir=ctx.run_dir, status="error")
        raise
