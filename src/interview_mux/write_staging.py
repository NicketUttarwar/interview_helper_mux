"""Per-stage write staging — outputs land in .pending_writes/ until auto-commit."""

from __future__ import annotations

import shutil
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from filelock import FileLock

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
    """v2 auto-commit disables operator write-approval pauses."""
    from interview_mux.v2.config import v2_auto_commit

    return not v2_auto_commit()


def active_stage() -> str | None:
    """Stage id currently executing (write staging context)."""
    return _active_stage.get()


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
    """Return staging path when a stage is active; else the committed run path."""
    sid = _active_stage.get()
    if not sid or is_operational_path(rel):
        return ctx.run_dir.joinpath(*rel.split("/"))
    return staged_path(ctx, rel, stage_id=sid)


def write_committed_json(
    ctx: RunContext,
    rel: str,
    data: Any,
    *,
    stage_key: str | None = None,
) -> Path:
    """Persist to the committed run tree without opening a new staging root."""
    if isinstance(data, dict):
        from interview_mux.artifact_writes import _prepare_for_disk_validation
        from interview_mux.prompt_validation import validate_artifact_write

        payload = _prepare_for_disk_validation(data, rel_path=rel, stage_key=stage_key)
        errors = validate_artifact_write(rel, payload)
        if errors:
            raise ValueError(
                f"{rel}: schema validation failed — " + "; ".join(errors[:6])
            )
        data = payload
    return write_mirrored_json(ctx, rel, data)


def write_mirrored_json(ctx: RunContext, rel: str, data: Any) -> Path:
    """Write JSON to the committed final path and update every pending staging copy."""
    final = ctx.final_path(*rel.split("/"))
    final.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(final, data)

    pending_root = ctx.run_dir / ".pending_writes"
    if pending_root.is_dir():
        for stage_dir in sorted(pending_root.iterdir()):
            if not stage_dir.is_dir():
                continue
            candidate = stage_dir.joinpath(*rel.split("/"))
            active = _active_stage.get()
            if candidate.is_file():
                fs_write_json(candidate, data)
            elif active and stage_dir.name == active and operator_visible_staging_path(active, rel):
                candidate.parent.mkdir(parents=True, exist_ok=True)
                fs_write_json(candidate, data)
                record_pending_approval(ctx, active)
    return final


def write_mirrored_text(ctx: RunContext, rel: str, text: str) -> Path:
    """Same as write_mirrored_json for plain-text artifacts."""
    final = ctx.final_path(*rel.split("/"))
    final.parent.mkdir(parents=True, exist_ok=True)
    fs_write_text(final, text)

    pending_root = ctx.run_dir / ".pending_writes"
    if pending_root.is_dir():
        for stage_dir in sorted(pending_root.iterdir()):
            if not stage_dir.is_dir():
                continue
            candidate = stage_dir.joinpath(*rel.split("/"))
            active = _active_stage.get()
            if candidate.is_file():
                fs_write_text(candidate, text)
            elif active and stage_dir.name == active and operator_visible_staging_path(active, rel):
                candidate.parent.mkdir(parents=True, exist_ok=True)
                fs_write_text(candidate, text)
                record_pending_approval(ctx, active)
    return final


def _transcript_has_operator_edits(doc: Any) -> bool:
    if not isinstance(doc, dict):
        return False
    if doc.get("review_applied_at"):
        return True
    words = doc.get("words") or []
    return any(isinstance(w, dict) and w.get("corrected") for w in words)


def _should_preserve_committed_transcript(ctx: RunContext, rel: str, staged_src: Path) -> bool:
    """True when promoting staged STT would clobber committed operator corrections."""
    if rel != "transcript/full.json":
        return False
    dest = ctx.run_dir.joinpath(*rel.split("/"))
    if not dest.is_file() or not staged_src.is_file():
        return False
    try:
        committed = fs_read_json(dest)
        staged = fs_read_json(staged_src)
    except Exception:
        return False
    return _transcript_has_operator_edits(committed) and not _transcript_has_operator_edits(staged)


def staging_approval_hint(ctx: RunContext, rel: str) -> str | None:
    if write_approval_enabled():
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
    return resolve_read_path(ctx, rel).is_file()


def _stage_output_spec_matches(rel: str, spec: str) -> bool:
    import fnmatch

    if spec.startswith("glob:"):
        return fnmatch.fnmatch(rel, spec[5:])
    if spec.endswith("/"):
        prefix = spec.rstrip("/") + "/"
        return rel == spec.rstrip("/") or rel.startswith(prefix)
    return rel == spec


_AUDIO_OUTPUT_SUFFIXES = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")


def expand_audio_output_paths(ctx: RunContext, specs: Iterable[str]) -> list[str]:
    """Resolve stage audio_outputs specs (exact, glob:, dir/) to relative file paths."""
    found: list[str] = []
    seen: set[str] = set()
    expandable = [s for s in specs if s.startswith("glob:") or s.endswith("/")]
    for spec in specs:
        if spec.startswith("glob:") or spec.endswith("/"):
            continue
        if artifact_exists_resolved(ctx, spec) and spec not in seen:
            found.append(spec)
            seen.add(spec)
    if expandable and ctx.run_dir.is_dir():
        for p in sorted(ctx.run_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ctx.run_dir).as_posix()
            if rel in seen or not rel.lower().endswith(_AUDIO_OUTPUT_SUFFIXES):
                continue
            if any(_stage_output_spec_matches(rel, spec) for spec in expandable):
                found.append(rel)
                seen.add(rel)
    return sorted(found)


def operator_visible_staging_path(stage_id: str, rel: str) -> bool:
    """True when a staged relative path is an operator-facing stage output."""
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID.get(stage_id)
    if not info:
        return True
    specs = tuple(info.artifacts) + tuple(info.editable) + tuple(info.audio_outputs)
    if not specs:
        return True
    return any(_stage_output_spec_matches(rel, spec) for spec in specs)


def list_stage_staging_paths(ctx: RunContext, stage_id: str) -> list[str]:
    root = staging_root(ctx, stage_id)
    if not root.is_dir():
        return []
    paths: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != ".write.lock":
            rel = str(p.relative_to(root)).replace("\\", "/")
            if operator_visible_staging_path(stage_id, rel):
                paths.append(rel)
    return paths


def list_pending_paths(ctx: RunContext, stage_id: str) -> list[str]:
    return list_stage_staging_paths(ctx, stage_id)


def resolve_pending_stage_for_path(ctx: RunContext, stage_id: str, rel: str) -> str:
    return stage_id


def clear_segmentation_classification_on_boundary_restage(ctx: RunContext) -> None:
    """No-op in v2 — segmentation uses standard per-stage staging."""
    return None


def pending_stage_for_path(ctx: RunContext, rel: str) -> str | None:
    if is_operational_path(rel):
        return None
    meta_path = ctx.run_dir / "run_meta.json"
    if meta_path.is_file():
        meta = ctx.read_json("run_meta.json")
        if isinstance(meta, dict):
            pending = meta.get("pending_write_approval") or {}
            if isinstance(pending, dict):
                for sid, info in pending.items():
                    paths = info.get("paths") if isinstance(info, dict) else None
                    if isinstance(paths, list) and rel in paths:
                        return str(sid)
    pending_root = ctx.run_dir / ".pending_writes"
    if not pending_root.is_dir():
        return None
    for stage_dir in sorted(pending_root.iterdir()):
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
            if not operator_visible_staging_path(stage_id, rel):
                continue
            if _should_preserve_committed_transcript(ctx, rel, src):
                ctx.log(
                    f"Keeping operator-corrected {rel} — skipped stale staged copy from {stage_id}.",
                    level="warning",
                    stage=stage_id,
                    action_id="write_staging.flush",
                    detail={"event": "preserve_corrected_transcript", "path": rel},
                )
                continue
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
                    action_id="write_staging.flush",
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
                            action_id="write_staging.flush",
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


def all_pending_stages(ctx: RunContext, *, savable_only: bool = True) -> list[str]:
    stages: list[str] = []
    root = ctx.run_dir / ".pending_writes"
    if root.is_dir():
        stages.extend(
            p.name
            for p in sorted(root.iterdir())
            if p.is_dir() and list_pending_paths(ctx, p.name)
        )
    meta_path = ctx.run_dir / "run_meta.json"
    if meta_path.is_file():
        meta = ctx.read_json("run_meta.json")
        pending = meta.get("pending_write_approval") if isinstance(meta, dict) else {}
        if isinstance(pending, dict):
            for sid, info in pending.items():
                if sid in stages:
                    continue
                paths = info.get("paths") if isinstance(info, dict) else None
                if isinstance(paths, list) and paths:
                    stages.append(str(sid))
    if savable_only:
        return [sid for sid in stages if write_approval_save_blocked_reason(ctx, sid) is None]
    return stages


def read_pending_json(ctx: RunContext, stage_id: str, rel: str) -> Any:
    return fs_read_json(staged_path(ctx, rel, stage_id=stage_id))


def read_pending_text(ctx: RunContext, stage_id: str, rel: str) -> str:
    return fs_read_text(staged_path(ctx, rel, stage_id=stage_id))


class WriteApprovalBlockedError(Exception):
    """Staged save blocked — stage failed a quality gate."""

    def __init__(self, stage_id: str, message: str) -> None:
        self.stage_id = stage_id
        super().__init__(message)


class WriteApprovalPending(Exception):
    """Pipeline paused until operator approves staged writes (legacy only)."""

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
    job = read_gui_job(ctx) or {}
    if not isinstance(job, dict):
        job = {}
    job["status"] = "gate"
    job["stage"] = stage_id
    job["message"] = message
    ctx.write_json("gui_job.json", job, skip_handoff=True)


def gate_blocked_stage(ctx: RunContext) -> str | None:
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
    return False


def is_stage_gate_blocked(ctx: RunContext, stage_id: str) -> bool:
    return is_llm_gate_blocked(ctx, stage_id)


def write_approval_save_blocked_reason(ctx: RunContext, stage_id: str) -> str | None:
    if not write_approval_enabled() or not has_pending_writes(ctx, stage_id):
        return None
    if is_stage_gate_blocked(ctx, stage_id):
        job = read_gui_job(ctx) or {}
        return str(
            job.get("message")
            or (
                f"Stage {stage_id} failed the LLM quality gate — "
                "re-run or discard staged outputs instead of saving."
            )
        )
    from interview_mux.stage_completion import staged_artifacts_acceptable

    ok, reason = staged_artifacts_acceptable(ctx, stage_id)
    if not ok:
        return reason
    return None


def write_approval_allowed(ctx: RunContext, stage_id: str) -> bool:
    if not write_approval_enabled():
        return False
    if write_approval_save_blocked_reason(ctx, stage_id):
        return False
    return has_pending_writes(ctx, stage_id)


def assert_write_approval_allowed(ctx: RunContext, stage_id: str) -> None:
    if is_stage_gate_blocked(ctx, stage_id):
        job = read_gui_job(ctx) or {}
        msg = str(
            job.get("message")
            or (
                f"Stage {stage_id} failed the LLM quality gate — "
                "re-run or discard staged outputs instead of saving."
            )
        )
        raise WriteApprovalBlockedError(stage_id, msg)
    from interview_mux.stage_completion import staged_artifacts_acceptable

    ok, reason = staged_artifacts_acceptable(ctx, stage_id)
    if not ok:
        raise WriteApprovalBlockedError(stage_id, reason)
    if not has_pending_writes(ctx, stage_id):
        raise FileNotFoundError(f"No pending writes for stage: {stage_id}")


def _commit_stage_writes(ctx: RunContext, stage_id: str) -> list[str]:
    """Promote staged outputs and mark the stage done (v2 auto-commit)."""
    if not has_pending_writes(ctx, stage_id):
        return []
    return approve_stage_writes(ctx, stage_id)


def after_stage_write_check(ctx: RunContext, stage_id: str) -> None:
    if not has_pending_writes(ctx, stage_id):
        return
    if write_approval_enabled():
        record_pending_approval(ctx, stage_id)
        raise WriteApprovalPending(stage_id, list_pending_paths(ctx, stage_id))
    _commit_stage_writes(ctx, stage_id)


def run_wrapped_stage(ctx: RunContext, stage_id: str, fn: Any) -> None:
    """Execute a stage function with write staging and v2 auto-commit."""
    from interview_mux.operator_trace import active_run_context, log_step

    ctx_token = active_run_context.set(ctx)
    stage_action_id = f"pipeline.stage.{stage_id}"
    try:
        log_step(
            f"Preparing stage: {stage_id}",
            ctx=ctx,
            stage=stage_id,
            detail={"action_id": stage_action_id, "event": "stage_start"},
        )
        from interview_mux.stage_input_checks import require_stage_inputs

        require_stage_inputs(ctx, stage_id)
        from interview_mux.llm_flow_hardening import maybe_require_upstream_llm_progress

        maybe_require_upstream_llm_progress(ctx, stage_id)
        enter_stage_staging(stage_id)
        try:
            fn()
            ctx.log(
                f"Stage finished: {stage_id}",
                level="success",
                stage=stage_id,
                action_id=stage_action_id,
                detail={"journey_kind": "execute", "event": "stage_finish"},
            )
        except WriteApprovalPending:
            raise
        except Exception as exc:
            from interview_mux.operator_trace import log_stage_error

            log_stage_error(stage_id, exc, ctx=ctx)
            raise
        finally:
            exit_stage_staging()
        after_stage_write_check(ctx, stage_id)
    finally:
        active_run_context.reset(ctx_token)


def check_write_approval_before_execute(
    ctx: RunContext,
    stage_id: str | None = None,
) -> WriteApprovalPending | None:
    """v2 auto-commit — execute is never blocked by pending writes."""
    if not write_approval_enabled():
        return None
    stages = all_pending_stages(ctx)
    if not stages:
        return None
    sid = stage_id or stages[0]
    paths = list_pending_paths(ctx, sid)
    if paths:
        return WriteApprovalPending(sid, paths)
    return None


def approve_batch_stage_writes(ctx: RunContext, stages: list[str] | None = None) -> dict[str, Any]:
    pending = all_pending_stages(ctx)
    if stages is None:
        stages = list(pending)
    else:
        stages = [s for s in stages if s in pending or has_pending_writes(ctx, s)]

    results: dict[str, Any] = {"approved": {}, "errors": {}, "phases": {}}
    for sid in stages:
        try:
            assert_write_approval_allowed(ctx, sid)
            flushed = approve_stage_writes(ctx, sid)
            results["approved"][sid] = flushed
        except Exception as exc:
            results["errors"][sid] = str(exc)
    ctx.log(
        f"Batch write approval: {len(results['approved'])} stage(s) saved"
        + (f", {len(results['errors'])} error(s)" if results["errors"] else ""),
        level="success" if not results["errors"] else "warning",
        stage="write_staging",
        action_id="write_staging.batch_approve",
        detail={
            "event": "write_approval_batch",
            "approved_stages": list(results["approved"].keys()),
            "error_stages": list(results["errors"].keys()),
        },
    )
    return results


def segmentation_pair_approve_needed(ctx: RunContext, stage_id: str) -> bool:
    return False


def approve_segmentation_pair_writes(ctx: RunContext) -> list[str]:
    return approve_stage_writes(ctx, "segment_classification")


def approve_stage_writes(ctx: RunContext, stage_id: str) -> list[str]:
    from interview_mux.operator_action_trace import begin_action, end_action

    trace_id = begin_action(
        "write_staging.approve",
        run_dir=ctx.run_dir,
        stage=stage_id,
        origin="api",
        summary=f"Approve staged writes for {stage_id}",
        function="write_staging.approve_stage_writes",
    )
    try:
        if stage_id in ("segment_classification", "content_brief_reanchor", "content_context", "boundary_detection"):
            from interview_mux.artifact_repairs import sync_content_brief_topic_segment_ids

            sync_content_brief_topic_segment_ids(ctx, overlay_stage=stage_id)
        flushed = flush_stage_writes(ctx, stage_id)
        from interview_mux.artifact_lifecycle import apply_fingerprints_on_flush, post_commit_validate

        apply_fingerprints_on_flush(ctx, stage_id, flushed)
        post_errors = post_commit_validate(ctx, stage_id)
        if post_errors:
            raise ValueError(
                "Post-commit validation failed: " + "; ".join(post_errors[:4])
            )
        if "segments/manifest.json" in flushed and ctx.artifact_exists("segments/manifest.json"):
            from interview_mux.artifact_completeness import hydrate_manifest_from_boundaries

            manifest = ctx.read_json("segments/manifest.json")
            hydrated = hydrate_manifest_from_boundaries(ctx, manifest)
            if hydrated != manifest:
                ctx.write_json("segments/manifest.json", hydrated, stage_key=stage_id)
        from interview_mux.stage_completion import assert_stage_artifacts_complete

        assert_stage_artifacts_complete(ctx, stage_id)
        ctx.mark_done(stage_id)
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
