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


VALID_ACTIVE_TABS = frozenset({"start", "executions", "pipeline", "logs"})
VALID_PIPELINE_SUB_TABS = frozenset(
    {"stage", "story", "timeline", "profile", "files", "llm_calls", "volley_memory"}
)


def set_active_execution(run_id: str, **extra: Any) -> dict[str, Any]:
    current = get_active_execution() or {}
    if str(current.get("run_id") or "") != str(run_id):
        current = {}
    payload: dict[str, Any] = {
        **current,
        "run_id": run_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    write_json(active_execution_path(), payload)
    return payload


def merge_active_execution(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge partial session updates into active_execution.json."""
    current = get_active_execution() or {}
    run_id = updates.get("run_id", current.get("run_id"))
    if not run_id:
        raise ValueError("run_id required to update active session")
    payload: dict[str, Any] = {**current, "run_id": str(run_id)}
    for key in ("selected_stage_id", "active_tab", "pipeline_sub_tab", "source_locked", "input_audio_path"):
        if key in updates:
            payload[key] = updates[key]
    tab = payload.get("active_tab")
    if tab is not None and tab not in VALID_ACTIVE_TABS:
        raise ValueError(f"Invalid active_tab: {tab}")
    sub = payload.get("pipeline_sub_tab")
    if sub is not None and sub not in VALID_PIPELINE_SUB_TABS:
        raise ValueError(f"Invalid pipeline_sub_tab: {sub}")
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(active_execution_path(), payload)
    return payload


def active_run_id() -> str | None:
    active = get_active_execution()
    if not active:
        return None
    rid = active.get("run_id")
    return str(rid) if rid else None


def source_audio_locked_for_session() -> bool:
    active = get_active_execution()
    if not active or not active.get("run_id"):
        return False
    return bool(active.get("source_locked", True))


def assert_session_allows_run_switch(target_run_id: str | None) -> None:
    """Raise ValueError when the GUI session has a locked source and switches runs."""
    active = get_active_execution()
    if not active or not active.get("run_id"):
        return
    if not source_audio_locked_for_session():
        return
    current = str(active["run_id"])
    if target_run_id is None:
        return
    if target_run_id != current:
        raise ValueError(
            "Source audio is locked for this session. Clear session before opening another execution."
        )


def clear_active_execution() -> None:
    p = active_execution_path()
    if p.is_file():
        p.unlink()


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
