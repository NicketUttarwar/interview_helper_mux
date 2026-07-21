"""Operator-visible step tracing — one log line minimum per substep, API call, or command."""

from __future__ import annotations

import traceback
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
    from interview_mux.write_staging import active_stage

    return active_stage() or "pipeline"


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
    run.log(message, level=level, stage=sid, detail=merged, action_id=merged.get("action_id"), origin=merged.get("origin"))


def log_api_call(
    provider: str,
    operation: str,
    *,
    ctx: RunContext | None = None,
    stage: str | None = None,
    detail: dict[str, Any] | None = None,
    action_id: str = "llm.api_call",
) -> None:
    """Log an external API or cloud CLI invocation before it runs."""
    payload: dict[str, Any] = {
        "provider": provider,
        "operation": operation,
        "journey_kind": "execute",
        "action_id": action_id,
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


class StageSubstepError(Exception):
    """Substep failure with an operator-visible label."""

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.stage = stage
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause


def failure_detail(exc: BaseException) -> dict[str, Any]:
    """Structured failure payload for operator logs."""
    return {
        "journey_kind": "execute",
        "event": "substep_fail",
        "error_class": type(exc).__name__,
        "traceback": traceback.format_exc(),
    }


def log_failure(
    message: str,
    exc: BaseException,
    *,
    ctx: RunContext | None = None,
    stage: str | None = None,
    detail: str | dict[str, Any] | None = None,
) -> None:
    """Log an exception with traceback and error class."""
    payload = failure_detail(exc)
    if isinstance(detail, dict):
        payload.update(detail)
    elif detail is not None:
        payload["detail"] = detail
    log_step(message, ctx=ctx, stage=stage, level="error", detail=payload)


def log_stage_error(
    stage: str,
    exc: BaseException,
    *,
    ctx: RunContext | None = None,
    label: str | None = None,
) -> None:
    """Log a stage-level failure with traceback and error class."""
    desc = label or f"Stage {stage}"
    log_failure(f"Failed: {desc}", exc, ctx=ctx, stage=stage)


@contextmanager
def logged_step(
    label: str,
    *,
    ctx: RunContext | None = None,
    stage: str | None = None,
    action_id: str | None = None,
) -> Iterator[None]:
    """Context manager that logs start, success, or failure for a named substep."""
    run = resolve_ctx(ctx)
    trace_id = None
    aid = action_id or f"pipeline.substep.{label.replace('/', '.')}"
    if run:
        from interview_mux.operator_action_trace import begin_action, end_action

        trace_id = begin_action(
            aid,
            run_dir=run.run_dir,
            stage=resolve_stage(stage),
            origin="pipeline",
            summary=label,
            function="operator_trace.logged_step",
        )
    log_step(f"Start: {label}", ctx=ctx, stage=stage, level="action", detail={"action_id": aid})
    try:
        yield
        log_step(f"Done: {label}", ctx=ctx, stage=stage, level="success", detail={"action_id": aid})
        if run and trace_id:
            from interview_mux.operator_action_trace import end_action

            end_action(trace_id, run_dir=run.run_dir, status="ok")
    except Exception as exc:
        log_step(
            f"Failed: {label}",
            ctx=ctx,
            stage=stage,
            level="error",
            detail={**failure_detail(exc), "action_id": aid},
        )
        if run and trace_id:
            from interview_mux.operator_action_trace import end_action

            end_action(trace_id, run_dir=run.run_dir, status="error")
        raise
