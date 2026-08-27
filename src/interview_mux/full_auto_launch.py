"""In-app Full-auto launch helpers (GUI Start page → detached driver)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from interview_mux.config import repo_root


def _tools_dir() -> Path:
    return repo_root() / "tools"


def launch_partial_auto_for_run(
    *,
    run_id: str,
    input_audio: str,
    keep_gui_server: bool = True,
) -> dict[str, Any]:
    """Start partially-accelerated driver (Full-auto stack; G0 + S3 require operator)."""
    tools = str(_tools_dir())
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from full_auto_daemon_launch import (  # type: ignore[import-not-found]
        launch_partial_auto_for_run as _launch,
    )

    return dict(
        _launch(
            run_id=run_id,
            input_audio=input_audio,
            keep_gui_server=keep_gui_server,
        )
    )


def shutdown_automation_stack(*, keep_gui_server: bool = True) -> dict[str, Any]:
    """Stop detached Full-auto / partially-accelerated driver + keepalive; optional serve."""
    tools = str(_tools_dir())
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from full_auto_daemon_launch import shutdown_full_auto_stack  # type: ignore[import-not-found]

    return dict(
        shutdown_full_auto_stack(
            kill_e2e=True,
            kill_server=not keep_gui_server,
        )
    )


def launch_full_auto_for_run(
    *,
    run_id: str,
    input_audio: str,
    keep_gui_server: bool = True,
) -> dict[str, Any]:
    """Start a run-scoped Full-auto driver without recycling the live GUI server."""
    tools = str(_tools_dir())
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from full_auto_daemon_launch import (  # type: ignore[import-not-found]
        launch_full_auto_for_run as _launch,
    )

    return dict(
        _launch(
            run_id=run_id,
            input_audio=input_audio,
            keep_gui_server=keep_gui_server,
        )
    )


def normalize_run_mode(raw: str | None) -> str:
    token = str(raw or "manual").strip().lower().replace(" ", "").replace("_", "-")
    if token in {"full-auto", "fullauto", "auto", "e2e"}:
        return "full-auto"
    if token in {"partially-accelerated", "partial-auto", "partiallyaccelerated"}:
        return "partially-accelerated"
    return "manual"
