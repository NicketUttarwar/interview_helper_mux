"""In-process hooks for updating gui_job.json during multi-stage batch runs."""

from __future__ import annotations

from typing import Callable

_StageHook = Callable[[str, int, int, list[str]], None]
_hooks: dict[str, _StageHook] = {}


def register_job_progress(run_id: str, hook: _StageHook) -> None:
    _hooks[run_id] = hook


def clear_job_progress(run_id: str) -> None:
    _hooks.pop(run_id, None)


def notify_stage_start(
    run_id: str,
    stage_id: str,
    *,
    index: int,
    total: int,
    stages_planned: list[str],
) -> None:
    hook = _hooks.get(run_id)
    if hook is not None:
        hook(stage_id, index, total, stages_planned)
