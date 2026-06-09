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


def active_staging_stage() -> str | None:
    return _active_stage.get()


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


def flush_stage_writes(ctx: RunContext, stage_id: str) -> list[str]:
    with _staging_lock(ctx, stage_id):
        root = staging_root(ctx, stage_id)
        if not root.is_dir():
            clear_pending_approval(ctx, stage_id)
            return []
        flushed: list[str] = []
        for src in sorted(root.rglob("*")):
            if not src.is_file() or src.name.endswith(".lock"):
                continue
            rel = str(src.relative_to(root)).replace("\\", "/")
            dest = ctx.run_dir.joinpath(*rel.split("/"))
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
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


def pending_approval_stage(ctx: RunContext) -> str | None:
    if not ctx.artifact_exists("run_meta.json"):
        return None
    meta = ctx.read_json("run_meta.json")
    if not isinstance(meta, dict):
        return None
    pending = meta.get("pending_write_approval") or {}
    if not isinstance(pending, dict) or not pending:
        return None
    return next(iter(pending.keys()), None)


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


class WriteApprovalPending(Exception):
    """Pipeline paused until operator approves staged writes."""

    def __init__(self, stage_id: str, paths: list[str]) -> None:
        self.stage_id = stage_id
        self.paths = paths
        super().__init__(
            f"Stage '{stage_id}' outputs await review before saving ({len(paths)} file(s))."
        )


def after_stage_write_check(ctx: RunContext, stage_id: str) -> None:
    if write_approval_enabled() and has_pending_writes(ctx, stage_id):
        record_pending_approval(ctx, stage_id)
        raise WriteApprovalPending(stage_id, list_pending_paths(ctx, stage_id))


def run_wrapped_stage(ctx: RunContext, stage_id: str, fn: Any) -> None:
    """Execute a stage function with optional write staging."""
    if write_approval_enabled():
        enter_stage_staging(stage_id)
    try:
        fn()
    finally:
        if write_approval_enabled():
            exit_stage_staging()
    after_stage_write_check(ctx, stage_id)


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
    flushed = flush_stage_writes(ctx, stage_id)
    ctx.mark_done(stage_id, force=True)
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if isinstance(meta, dict):
        ack = dict(meta.get("handoff_ack") or {})
        ack[stage_id] = datetime.now(timezone.utc).isoformat()
        meta["handoff_ack"] = ack
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        ctx.write_json("run_meta.json", meta, skip_handoff=True)
    return flushed
