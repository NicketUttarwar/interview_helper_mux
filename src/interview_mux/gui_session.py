"""GUI session persistence — delegates to application_session."""

from __future__ import annotations

from pathlib import Path

from interview_mux.application_session import (
    VALID_ACTIVE_TABS,
    VALID_ACTIVITY_LOG_TABS,
    VALID_PIPELINE_SUB_TABS,
    active_execution_path,
    active_run_id,
    assert_session_allows_run_switch,
    clear_active_execution,
    clear_session_files,
    get_active_execution,
    get_server_session,
    gui_dir,
    merge_active_execution,
    on_server_start,
    server_session_path,
    set_active_execution,
    source_audio_locked_for_session,
    touch_server_session,
)

__all__ = [
    "VALID_ACTIVE_TABS",
    "VALID_ACTIVITY_LOG_TABS",
    "VALID_PIPELINE_SUB_TABS",
    "active_execution_path",
    "server_session_path",
    "gui_dir",
    "get_active_execution",
    "set_active_execution",
    "merge_active_execution",
    "active_run_id",
    "source_audio_locked_for_session",
    "assert_session_allows_run_switch",
    "clear_active_execution",
    "touch_server_session",
    "get_server_session",
    "clear_session_files",
    "on_server_start",
]
