"""Immediate-previous execution resolution for session reuse."""

from __future__ import annotations

from typing import Any

from interview_mux.application_session import get_lineage, set_lineage
from interview_mux.journey_state import read_run_meta
from interview_mux.run_context import RunContext
from interview_mux.stage_execution_reuse import source_audio_hashes_match


def find_run_by_execution_number(n: int) -> str | None:
    for run_id in RunContext.list_runs():
        if not RunContext.exists(run_id):
            continue
        ctx = RunContext(run_id, create=False)
        meta = read_run_meta(ctx)
        num = meta.get("execution_number")
        if num is not None and int(num) == int(n):
            return run_id
    return None


def latest_execution_run_id(*, exclude: str | None = None) -> str | None:
    best_id: str | None = None
    best_n = -1
    for run_id in RunContext.list_runs():
        if exclude and run_id == exclude:
            continue
        if not RunContext.exists(run_id):
            continue
        ctx = RunContext(run_id, create=False)
        meta = read_run_meta(ctx)
        num = meta.get("execution_number")
        if num is None:
            continue
        n = int(num)
        if n > best_n:
            best_n = n
            best_id = run_id
    return best_id


def resolve_immediate_previous_run_id(current: RunContext) -> str | None:
    meta = read_run_meta(current)
    stored = meta.get("immediate_previous_run_id")
    if isinstance(stored, str) and stored and RunContext.exists(stored):
        return stored
    lineage = get_lineage()
    lid = lineage.get("immediate_previous_run_id")
    if isinstance(lid, str) and lid and RunContext.exists(lid) and lid != current.run_id:
        return lid
    n = meta.get("execution_number")
    if n is not None and int(n) > 1:
        prev = find_run_by_execution_number(int(n) - 1)
        if prev and prev != current.run_id:
            return prev
    return None


def resolve_previous_execution(current: RunContext) -> RunContext | None:
    prev_id = resolve_immediate_previous_run_id(current)
    if not prev_id:
        return None
    return RunContext(prev_id, create=False)


def hash_match_with_previous(current: RunContext) -> bool:
    prev = resolve_previous_execution(current)
    if not prev:
        return False
    return source_audio_hashes_match(current, prev)


def previous_run_summary(run_id: str) -> dict[str, Any] | None:
    if not RunContext.exists(run_id):
        return None
    summary = RunContext.summarize_run(run_id)
    ctx = RunContext(run_id, create=False)
    done = sum(1 for p in ctx.run_dir.joinpath(".stage_done").glob("*") if p.is_file()) if (
        ctx.run_dir.joinpath(".stage_done").is_dir()
    ) else 0
    meta = read_run_meta(ctx)
    return {
        **summary,
        "stages_done": done,
        "source_audio_hash_short": meta.get("source_audio_hash_short"),
    }


def record_immediate_previous_on_create(new_ctx: RunContext) -> str | None:
    prev_id = latest_execution_run_id(exclude=new_ctx.run_id)
    if not prev_id:
        return None

    def _patch(meta: dict[str, Any]) -> None:
        meta["immediate_previous_run_id"] = prev_id

    new_ctx.mutate_run_meta(_patch)
    set_lineage(immediate_previous_run_id=prev_id)
    return prev_id


def backfill_immediate_previous_run_id(ctx: RunContext) -> str | None:
    meta = read_run_meta(ctx)
    if meta.get("immediate_previous_run_id"):
        return str(meta["immediate_previous_run_id"])
    n = meta.get("execution_number")
    if n is not None and int(n) > 1:
        prev = find_run_by_execution_number(int(n) - 1)
        if prev:
            def _patch(m: dict[str, Any]) -> None:
                m["immediate_previous_run_id"] = prev

            ctx.mutate_run_meta(_patch)
            return prev
    return None
