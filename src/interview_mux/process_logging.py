"""Process-wide logging when launched via scripts/run.sh.

Operator-visible errors stay in gui_log.jsonl (canonical). When MUX_MIRROR_OPERATOR_ERRORS
is set, error-level entries are also written to stderr on the terminal that started run.sh.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

_OPERATOR_ERROR_LEVELS = frozenset({"error"})


def launched_via_run_sh() -> bool:
    return os.environ.get("MUX_LAUNCHED_VIA", "").strip() == "run.sh"


def operator_error_mirror_enabled() -> bool:
    raw = os.environ.get("MUX_MIRROR_OPERATOR_ERRORS", "")
    if raw.strip():
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return launched_via_run_sh()


def configure_process_logging() -> None:
    """Route Python logging ERROR+ to stderr; suppress noisy loggers when run via run.sh."""
    if not (operator_error_mirror_enabled() or launched_via_run_sh()):
        return

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stderr_handler)
    root.setLevel(logging.ERROR)

    for name in ("uvicorn", "uvicorn.error", "fastapi"):
        log = logging.getLogger(name)
        log.handlers.clear()
        log.propagate = True

    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.setLevel(logging.CRITICAL)


def serve_uvicorn_options() -> dict[str, Any]:
    """Uvicorn kwargs: errors only on terminal when started from run.sh."""
    if launched_via_run_sh():
        return {"log_level": "error", "access_log": False}
    return {"log_level": "info", "access_log": True}


def mirror_operator_entry(entry: dict[str, Any]) -> None:
    """Echo gui_log error lines to stderr (run.sh terminal)."""
    if not operator_error_mirror_enabled():
        return
    level = str(entry.get("level") or "info").lower()
    if level not in _OPERATOR_ERROR_LEVELS:
        return
    ts = entry.get("ts") or ""
    stage = entry.get("stage")
    message = entry.get("message") or ""
    prefix = f"{ts} [ERROR]"
    if stage:
        prefix = f"{prefix} [{stage}]"
    print(f"{prefix} {message}", file=sys.stderr, flush=True)
    detail = entry.get("detail")
    if detail:
        for line in str(detail).splitlines():
            print(f"  {line}", file=sys.stderr, flush=True)
