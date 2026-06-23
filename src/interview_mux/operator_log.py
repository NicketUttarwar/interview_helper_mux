"""Single entry point for operator-visible log lines (gui_log.jsonl)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from interview_mux.session_log import append_log

Origin = Literal["gui", "api", "cli", "subprocess", "pipeline", "system"]


def _merge_detail(
    detail: str | dict[str, Any] | None,
    *,
    action_id: str | None,
    origin: Origin | None,
) -> dict[str, Any] | str | None:
    base: dict[str, Any] = {}
    if isinstance(detail, dict):
        base.update(detail)
    elif detail is not None:
        base["detail"] = detail
    if action_id:
        base["action_id"] = action_id
    if origin:
        base["origin"] = origin
    return base if base else None


def operator_log(
    message: str,
    *,
    run_dir: Path | None = None,
    ctx: Any | None = None,
    level: str = "info",
    stage: str | None = None,
    action_id: str | None = None,
    origin: Origin | None = None,
    detail: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one line to gui_log.jsonl with normalized detail fields."""
    if ctx is not None and run_dir is None:
        run_dir = ctx.run_dir
    if run_dir is None:
        raise ValueError("operator_log requires run_dir or ctx")
    merged = _merge_detail(detail, action_id=action_id, origin=origin)
    return append_log(run_dir, message, level=level, stage=stage, detail=merged)
