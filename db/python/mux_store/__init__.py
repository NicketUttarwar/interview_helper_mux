"""SQLite-backed canonical store for interview_helper_mux (docs + runtime)."""

from mux_store.db import connect, init_db
from mux_store.repo_config import default_assets_path, default_sqlite_path, read_json_config
from mux_store.run_config import (
    allocate_session_id,
    default_master_wav,
    resolve_active_session_id,
    resolve_input_audio_path,
    resolve_s3_uri,
    session_ingest_wav,
    set_active_session_id,
)
from mux_store.runtime import (
    add_execution_step,
    append_event,
    create_run,
    execution_kv_delete,
    execution_kv_get,
    execution_kv_set,
    register_asset,
    touch_run,
    upsert_interview,
    upsert_segment,
)
from mux_store.sync_docs import sync_markdown_tree

__all__ = [
    "add_execution_step",
    "allocate_session_id",
    "append_event",
    "connect",
    "create_run",
    "default_assets_path",
    "default_master_wav",
    "default_sqlite_path",
    "execution_kv_delete",
    "execution_kv_get",
    "execution_kv_set",
    "init_db",
    "read_json_config",
    "register_asset",
    "resolve_active_session_id",
    "resolve_input_audio_path",
    "resolve_s3_uri",
    "session_ingest_wav",
    "set_active_session_id",
    "sync_markdown_tree",
    "touch_run",
    "upsert_interview",
    "upsert_segment",
]
