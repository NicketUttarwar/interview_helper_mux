from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root
from interview_mux.file_store import read_json, write_json


def gui_dir() -> Path:
    cfg = merged_config()
    root = repo_root() / cfg.get("assets_root", "ASSETS") / ".gui"
    root.mkdir(parents=True, exist_ok=True)
    return root


def active_execution_path() -> Path:
    return gui_dir() / "active_execution.json"


def server_session_path() -> Path:
    return gui_dir() / "server_session.json"


def get_active_execution() -> dict[str, Any] | None:
    p = active_execution_path()
    if not p.is_file():
        return None
    return read_json(p)


def set_active_execution(run_id: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    write_json(active_execution_path(), payload)
    return payload


def touch_server_session(*, port: int, host: str = "127.0.0.1") -> dict[str, Any]:
    payload = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "host": host,
        "port": port,
    }
    write_json(server_session_path(), payload)
    return payload


def get_server_session() -> dict[str, Any] | None:
    p = server_session_path()
    if not p.is_file():
        return None
    return read_json(p)
