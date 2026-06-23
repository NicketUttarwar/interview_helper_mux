"""Unified application session state (ASSETS/.gui/application_state.json)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root
from interview_mux.file_store import read_json, write_json

SCHEMA_VERSION = 1
_STATE_PATH_NAME = "application_state.json"

VALID_ACTIVE_TABS = frozenset({"start", "executions", "pipeline", "logs"})
VALID_PIPELINE_SUB_TABS = frozenset(
    {"stage", "story", "timeline", "profile", "files", "llm_calls", "volley_memory"}
)
VALID_ACTIVITY_LOG_TABS = frozenset({"live", "step", "all"})


def gui_dir() -> Path:
    cfg = merged_config()
    root = repo_root() / cfg.get("assets_root", "ASSETS") / ".gui"
    root.mkdir(parents=True, exist_ok=True)
    return root


def active_execution_path() -> Path:
    return gui_dir() / "active_execution.json"


def server_session_path() -> Path:
    return gui_dir() / "server_session.json"


def application_state_path() -> Path:
    return gui_dir() / _STATE_PATH_NAME


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "server": {},
        "active": {},
        "source": {},
        "lineage": {},
        "client_hints": {},
    }


def _migrate_from_legacy() -> dict[str, Any]:
    state = _empty_state()
    active_path = active_execution_path()
    if active_path.is_file():
        legacy_active = read_json(active_path)
        if isinstance(legacy_active, dict):
            state["active"] = {
                k: legacy_active[k]
                for k in (
                    "run_id",
                    "selected_stage_id",
                    "active_tab",
                    "pipeline_sub_tab",
                    "activity_log_tab",
                    "activity_log_collapsed",
                    "pipeline_collapsed_stages",
                    "pipeline_expanded_done_stages",
                    "pipeline_filter_needs_you",
                    "updated_at",
                )
                if k in legacy_active
            }
            state["source"] = {
                "source_locked": legacy_active.get("source_locked", True),
                "input_audio_path": legacy_active.get("input_audio_path"),
            }
    server_path = server_session_path()
    if server_path.is_file():
        legacy_server = read_json(server_path)
        if isinstance(legacy_server, dict):
            state["server"] = {
                k: legacy_server[k]
                for k in ("started_at", "pid", "host", "port", "operator_session_id")
                if k in legacy_server
            }
    return state


def load_state() -> dict[str, Any]:
    path = application_state_path()
    if path.is_file():
        raw = read_json(path)
        if isinstance(raw, dict):
            if raw.get("schema_version") != SCHEMA_VERSION:
                raw["schema_version"] = SCHEMA_VERSION
            return raw
    return _migrate_from_legacy()


def save_state(state: dict[str, Any]) -> dict[str, Any]:
    state = {**state, "schema_version": SCHEMA_VERSION}
    write_json(application_state_path(), state)
    _sync_legacy_files(state)
    return state


def _sync_legacy_files(state: dict[str, Any]) -> None:
    """Keep legacy paths readable for older tooling during transition."""
    active = state.get("active") if isinstance(state.get("active"), dict) else {}
    source = state.get("source") if isinstance(state.get("source"), dict) else {}
    if active.get("run_id"):
        payload: dict[str, Any] = {
            **active,
            **{k: source[k] for k in ("source_locked", "input_audio_path") if k in source},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json(active_execution_path(), payload)
    server = state.get("server") if isinstance(state.get("server"), dict) else {}
    if server:
        write_json(server_session_path(), server)


def get_state() -> dict[str, Any]:
    return load_state()


def on_server_start(*, port: int, host: str = "127.0.0.1") -> dict[str, Any]:
    state = load_state()
    prev_session_id = (state.get("server") or {}).get("operator_session_id")
    operator_session_id = str(uuid.uuid4())
    state["server"] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "host": host,
        "port": port,
        "operator_session_id": operator_session_id,
    }
    lineage = dict(state.get("lineage") or {})
    if prev_session_id:
        lineage["previous_operator_session_id"] = prev_session_id
    state["lineage"] = lineage
    save_state(state)
    _write_operator_session_log(operator_session_id, f"Server started on {host}:{port}")
    return state["server"]


def _operator_sessions_dir() -> Path:
    root = gui_dir() / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_operator_session_log(operator_session_id: str, message: str) -> None:
    log_path = _operator_sessions_dir() / operator_session_id / "bootstrap.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{ts} {message}\n")


def get_active() -> dict[str, Any] | None:
    active = load_state().get("active")
    if not isinstance(active, dict) or not active.get("run_id"):
        return None
    return active


def get_server() -> dict[str, Any] | None:
    server = load_state().get("server")
    return server if isinstance(server, dict) and server else None


def get_lineage() -> dict[str, Any]:
    lineage = load_state().get("lineage")
    return dict(lineage) if isinstance(lineage, dict) else {}


def set_lineage(**updates: Any) -> dict[str, Any]:
    state = load_state()
    lineage = dict(state.get("lineage") or {})
    lineage.update(updates)
    state["lineage"] = lineage
    save_state(state)
    return lineage


def set_active_execution(run_id: str, **extra: Any) -> dict[str, Any]:
    state = load_state()
    current = state.get("active") if isinstance(state.get("active"), dict) else {}
    if str(current.get("run_id") or "") != str(run_id):
        current = {}
    active: dict[str, Any] = {
        **current,
        "run_id": run_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    state["active"] = active
    if "source_locked" in extra or "input_audio_path" in extra:
        source = dict(state.get("source") or {})
        if "source_locked" in extra:
            source["source_locked"] = extra["source_locked"]
        if "input_audio_path" in extra:
            source["input_audio_path"] = extra["input_audio_path"]
        state["source"] = source
    save_state(state)
    return active


def merge_active_execution(updates: dict[str, Any]) -> dict[str, Any]:
    state = load_state()
    current = state.get("active") if isinstance(state.get("active"), dict) else {}
    run_id = updates.get("run_id", current.get("run_id"))
    if not run_id:
        raise ValueError("run_id required to update active session")
    active: dict[str, Any] = {**current, "run_id": str(run_id)}
    for key in (
        "selected_stage_id",
        "active_tab",
        "pipeline_sub_tab",
        "activity_log_tab",
        "activity_log_collapsed",
        "pipeline_collapsed_stages",
        "pipeline_expanded_done_stages",
        "pipeline_filter_needs_you",
    ):
        if key in updates:
            active[key] = updates[key]
    tab = active.get("active_tab")
    if tab is not None and tab not in VALID_ACTIVE_TABS:
        raise ValueError(f"Invalid active_tab: {tab}")
    sub = active.get("pipeline_sub_tab")
    if sub is not None and sub not in VALID_PIPELINE_SUB_TABS:
        raise ValueError(f"Invalid pipeline_sub_tab: {sub}")
    log_tab = active.get("activity_log_tab")
    if log_tab is not None and log_tab not in VALID_ACTIVITY_LOG_TABS:
        raise ValueError(f"Invalid activity_log_tab: {log_tab}")
    active["updated_at"] = datetime.now(timezone.utc).isoformat()
    state["active"] = active
    source = dict(state.get("source") or {})
    for key in ("source_locked", "input_audio_path"):
        if key in updates:
            source[key] = updates[key]
    if source:
        state["source"] = source
    save_state(state)
    return active


def active_run_id() -> str | None:
    active = get_active()
    if not active:
        return None
    rid = active.get("run_id")
    return str(rid) if rid else None


def source_audio_locked_for_session() -> bool:
    active = get_active()
    if not active or not active.get("run_id"):
        return False
    state = load_state()
    source = state.get("source") if isinstance(state.get("source"), dict) else {}
    if "source_locked" in source:
        return bool(source.get("source_locked"))
    return bool(active.get("source_locked", True))


def assert_session_allows_run_switch(target_run_id: str | None) -> None:
    active = get_active()
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
    state = load_state()
    state["active"] = {}
    state["source"] = {}
    save_state(state)
    for p in (active_execution_path(),):
        if p.is_file():
            p.unlink()


def touch_server_session(*, port: int, host: str = "127.0.0.1") -> dict[str, Any]:
    return on_server_start(port=port, host=host)


def get_server_session() -> dict[str, Any] | None:
    return get_server()


def get_active_execution() -> dict[str, Any] | None:
    """Merged active + source for API compatibility."""
    active = get_active()
    if not active:
        return None
    state = load_state()
    source = state.get("source") if isinstance(state.get("source"), dict) else {}
    return {**active, **{k: source[k] for k in ("source_locked", "input_audio_path") if k in source}}


def build_session_payload() -> dict[str, Any]:
    from interview_mux.run_context import RunContext
    from interview_mux.session_lineage import (
        hash_match_with_previous,
        previous_run_summary,
        resolve_immediate_previous_run_id,
    )

    state = load_state()
    active = get_active_execution()
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "server": state.get("server"),
        "active": active,
        "lineage": dict(state.get("lineage") or {}),
    }
    if active and active.get("run_id"):
        rid = str(active["run_id"])
        if not RunContext.exists(rid):
            clear_active_execution()
            out["active"] = None
        else:
            ctx = RunContext(rid, create=False)
            from interview_mux.session_log import read_log

            out["log"] = read_log(ctx.run_dir, tail=200)
            out["run_summary"] = RunContext.summarize_run(rid)
            out["working_dir"] = str(ctx.run_dir)
            prev_id = resolve_immediate_previous_run_id(ctx)
            if prev_id:
                out["lineage"]["immediate_previous_run_id"] = prev_id
                out["lineage"]["hash_match_with_previous"] = hash_match_with_previous(ctx)
                out["previous_run_summary"] = previous_run_summary(prev_id)
    return out


def clear_session_files(*, fresh: bool = False) -> None:
    """Clear session state when launch requests a fresh GUI session."""
    if not fresh:
        return
    for name in (
        _STATE_PATH_NAME,
        "active_execution.json",
        "server_session.json",
        "api_consent.json",
        "active_execution.json.lock",
        "server_session.json.lock",
        "api_consent.json.lock",
    ):
        p = gui_dir() / name
        if p.is_file():
            p.unlink()
