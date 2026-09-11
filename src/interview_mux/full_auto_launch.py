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


def automation_driver_alive() -> bool:
    """True when a detached Full-auto / partially-accelerated driver is running."""
    tools = str(_tools_dir())
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from full_auto_daemon_launch import automation_driver_alive as _alive  # type: ignore[import-not-found]

    return bool(_alive())


def automation_driver_bound_run_id() -> str | None:
    """Run id the live automation driver is bound to (pointer / console), if any."""
    tools = str(_tools_dir())
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from full_auto_daemon_launch import driver_run_bound  # type: ignore[import-not-found]

    rid = driver_run_bound()
    return str(rid).strip() if rid else None


def alive_driver_run_mode(bound_run_id: str | None = None) -> str | None:
    """Normalize run_mode of the live driver from its run_meta, if readable."""
    rid = bound_run_id or automation_driver_bound_run_id()
    if not rid:
        return None
    try:
        from interview_mux.run_context import RunContext

        if not RunContext.exists(rid):
            return None
        ctx = RunContext(rid, create=False)
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if not isinstance(meta, dict):
            return None
        return normalize_run_mode(str(meta.get("run_mode") or ""))
    except Exception:
        return None


def refuse_dual_driver_launch(
    *,
    requested_run_id: str,
    requested_mode: str,
) -> dict[str, Any] | None:
    """D-04: 409 payload when alive driver conflicts; None when attach/launch OK.

    Same-run same-mode → idempotent attach (caller skips relaunch).
    Cross-run or Full↔Partial → conflict dict for HTTP 409.

    Unbound live driver + fresh create (no run_id / ``__new__``) is allowed: the
    CLI ``ensure_run`` path is already ``pgrep``-visible before ``POST /api/runs``
    binds a pointer, so treating that as dual-driver suicide-loops fresh kickoff.
    """
    if not automation_driver_alive():
        return None
    bound = automation_driver_bound_run_id()
    req = (requested_run_id or "").strip()
    # Mid-ensure_run: driver process alive, pointer not written yet.
    if not bound and (not req or req == "__new__"):
        return None
    alive_mode = alive_driver_run_mode(bound)
    req_mode = normalize_run_mode(requested_mode)
    if bound and bound == requested_run_id and alive_mode == req_mode:
        return {
            "attach": True,
            "driver_already_running": True,
            "bound_run_id": bound,
            "run_mode": alive_mode,
        }
    detail = {
        "error": "automation_driver_conflict",
        "bound_run_id": bound,
        "bound_run_mode": alive_mode,
        "requested_run_id": requested_run_id,
        "requested_run_mode": req_mode,
    }
    if bound and bound != requested_run_id:
        detail["message"] = (
            f"Automation driver already running for {bound}. "
            "Clear session / stop the driver before starting another execution."
        )
    elif alive_mode and alive_mode != req_mode:
        detail["message"] = (
            f"Automation driver is in {alive_mode} mode; cannot attach {req_mode}. "
            "Stop the driver or start the same mode for the same run."
        )
    else:
        detail["message"] = (
            "Automation driver already running. "
            "Stop it before launching Full-auto or Partially accelerated."
        )
    return detail


def shutdown_automation_stack(
    *,
    keep_gui_server: bool = True,
    keep_driver: bool = False,
) -> dict[str, Any]:
    """Stop detached Full-auto / partially-accelerated driver + keepalive; optional serve."""
    tools = str(_tools_dir())
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from full_auto_daemon_launch import shutdown_full_auto_stack  # type: ignore[import-not-found]

    return dict(
        shutdown_full_auto_stack(
            kill_e2e=not keep_driver,
            kill_server=not keep_gui_server,
            keep_driver=keep_driver,
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
