"""Hard-stop irreparable stage failures with operator-visible logging.

Writes an error line to ``gui_log.jsonl`` (Activity panel), mirrors to the
``run.sh`` terminal via ``MUX_MIRROR_OPERATOR_ERRORS``, and raises so the
pipeline / API aborts instead of silently continuing.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


class LoudStageFailure(RuntimeError):
    """Irreparable stage failure — pipeline must stop."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        reason: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.reason = reason
        self.detail = dict(detail or {})


def raise_loud_failure(
    ctx: RunContext,
    message: str,
    *,
    stage: str,
    reason: str,
    detail: dict[str, Any] | None = None,
    action_id: str | None = None,
    cause: BaseException | None = None,
) -> None:
    """Log at error level (GUI + terminal mirror) then raise ``LoudStageFailure``."""
    payload: dict[str, Any] = {
        "reason": reason,
        "hard_stop": True,
        **(detail or {}),
    }
    if cause is not None:
        payload["cause"] = f"{type(cause).__name__}: {cause}"
    ctx.log(
        message,
        level="error",
        stage=stage,
        action_id=action_id or "pipeline.loud_fail",
        detail=payload,
        origin="pipeline",
    )
    # Extra stderr line even when mirror is off — irreparable failures must be visible.
    import sys

    print(f"[HARD STOP] [{stage}] {message}", file=sys.stderr, flush=True)
    if cause is not None:
        print(f"  cause: {type(cause).__name__}: {cause}", file=sys.stderr, flush=True)
    for key in ("reason", "signals", "line_id", "line_ids"):
        if key in payload and payload[key] is not None:
            print(f"  {key}: {payload[key]}", file=sys.stderr, flush=True)

    exc = LoudStageFailure(message, stage=stage, reason=reason, detail=payload)
    if cause is not None:
        raise exc from cause
    raise exc
