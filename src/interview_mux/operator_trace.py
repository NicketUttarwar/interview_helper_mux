"""Operator-visible step tracing — one log line minimum per substep, API call, or command."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from interview_mux.run_context import RunContext

active_run_context: ContextVar[RunContext | None] = ContextVar("active_run_context", default=None)


def resolve_ctx(ctx: RunContext | None = None) -> RunContext | None:
    return ctx or active_run_context.get()


def resolve_stage(stage: str | None = None) -> str:
    if stage:
        return stage
    from interview_mux.custom_run_handoff import active_pipeline_stage

    return active_pipeline_stage.get() or "pipeline"


def log_step(
    message: str,
    *,
    ctx: RunContext | None = None,
    stage: str | None = None,
    level: str = "action",
    detail: str | dict[str, Any] | None = None,
) -> None:
    """Append one operator-visible log line when a run workspace is active."""
    run = resolve_ctx(ctx)
    if not run:
        return
    sid = resolve_stage(stage)
    merged: dict[str, Any] = {"journey_kind": "execute"}
    if isinstance(detail, dict):
        merged.update(detail)
    elif detail is not None:
        merged["detail"] = detail
    run.log(message, level=level, stage=sid, detail=merged)


def log_api_call(
    provider: str,
    operation: str,
    *,
    ctx: RunContext | None = None,
    stage: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Log an external API or cloud CLI invocation before it runs."""
    payload: dict[str, Any] = {
        "provider": provider,
        "operation": operation,
        "journey_kind": "execute",
    }
    if detail:
        payload.update(detail)
    log_step(
        f"{provider}: {operation}",
        ctx=ctx,
        stage=stage,
        level="action",
        detail=payload,
    )


@contextmanager
def logged_step(
    label: str,
    *,
    ctx: RunContext | None = None,
    stage: str | None = None,
) -> Iterator[None]:
    """Context manager that logs start, success, or failure for a named substep."""
    log_step(f"Start: {label}", ctx=ctx, stage=stage, level="action")
    try:
        yield
        log_step(f"Done: {label}", ctx=ctx, stage=stage, level="success")
    except Exception:
        log_step(f"Failed: {label}", ctx=ctx, stage=stage, level="error")
        raise
