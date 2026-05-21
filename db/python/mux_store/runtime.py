from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_run(
    conn: sqlite3.Connection,
    *,
    status: str = "pending",
    orchestration_slug: str | None = None,
    parent_run_id: str | None = None,
    git_revision: str | None = None,
    config: dict[str, Any] | None = None,
    runtime_context: dict[str, Any] | None = None,
    notes: str | None = None,
) -> str:
    run_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO execution_run (
          id, status, orchestration_slug, parent_run_id, git_revision,
          config_json, runtime_context_json, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            status,
            orchestration_slug,
            parent_run_id,
            git_revision,
            json.dumps(config or {}, sort_keys=True),
            json.dumps(runtime_context, sort_keys=True) if runtime_context else None,
            notes,
            _utc_iso(),
            _utc_iso(),
        ),
    )
    conn.commit()
    return run_id


def touch_run(conn: sqlite3.Connection, run_id: str, *, status: str | None = None, notes: str | None = None) -> None:
    if status is None and notes is None:
        conn.execute(
            "UPDATE execution_run SET updated_at = ? WHERE id = ?",
            (_utc_iso(), run_id),
        )
    else:
        conn.execute(
            """
            UPDATE execution_run
            SET updated_at = ?,
                status = COALESCE(?, status),
                notes = COALESCE(?, notes)
            WHERE id = ?
            """,
            (_utc_iso(), status, notes, run_id),
        )
    conn.commit()


def append_event(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    severity: str = "info",
    kind: str = "log",
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO run_event (run_id, ts, severity, kind, message, payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            _utc_iso(),
            severity,
            kind,
            message,
            json.dumps(payload, sort_keys=True) if payload else None,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_execution_step(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    step_order: int,
    stage_slug: str | None,
    state: str,
    started_at: str | None = None,
    ended_at: str | None = None,
    error_text: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO execution_step (
          run_id, step_order, stage_slug, state, started_at, ended_at, error_text, metrics_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id, step_order) DO UPDATE SET
          stage_slug = excluded.stage_slug,
          state = excluded.state,
          started_at = excluded.started_at,
          ended_at = excluded.ended_at,
          error_text = excluded.error_text,
          metrics_json = excluded.metrics_json
        """,
        (
            run_id,
            step_order,
            stage_slug,
            state,
            started_at,
            ended_at,
            error_text,
            json.dumps(metrics, sort_keys=True) if metrics else None,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def register_asset(
    conn: sqlite3.Connection,
    *,
    storage_uri: str,
    kind: str,
    run_id: str | None = None,
    interview_id: str | None = None,
    sha256: str | None = None,
    byte_length: int | None = None,
    mime_type: str | None = None,
    meta: dict[str, Any] | None = None,
    asset_id: str | None = None,
) -> str:
    aid = asset_id or str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO asset (
          id, run_id, interview_id, kind, storage_uri, sha256, byte_length, mime_type, meta_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            aid,
            run_id,
            interview_id,
            kind,
            storage_uri,
            sha256,
            byte_length,
            mime_type,
            json.dumps(meta, sort_keys=True) if meta else None,
            _utc_iso(),
        ),
    )
    conn.commit()
    return aid


def upsert_interview(conn: sqlite3.Connection, interview_id: str, *, title: str | None = None, meta: dict[str, Any] | None = None) -> None:
    conn.execute(
        """
        INSERT INTO interview (id, title, meta_json, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          title = COALESCE(excluded.title, interview.title),
          meta_json = COALESCE(excluded.meta_json, interview.meta_json)
        """,
        (interview_id, title, json.dumps(meta, sort_keys=True) if meta else None, _utc_iso()),
    )
    conn.commit()


def upsert_segment(
    conn: sqlite3.Connection,
    *,
    interview_id: str,
    segment_id: str,
    t_start_ms: int,
    t_end_ms: int,
    text: str | None = None,
    transcript_revision_id: str | None = None,
    scores: dict[str, Any] | None = None,
    flags: dict[str, Any] | None = None,
    mutex_group_id: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO segment (
          segment_id, interview_id, transcript_revision_id, t_start_ms, t_end_ms,
          text, scores_json, flags_json, mutex_group_id, provenance_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(interview_id, segment_id) DO UPDATE SET
          transcript_revision_id = excluded.transcript_revision_id,
          t_start_ms = excluded.t_start_ms,
          t_end_ms = excluded.t_end_ms,
          text = excluded.text,
          scores_json = excluded.scores_json,
          flags_json = excluded.flags_json,
          mutex_group_id = excluded.mutex_group_id,
          provenance_json = excluded.provenance_json,
          updated_at = excluded.updated_at
        """,
        (
            segment_id,
            interview_id,
            transcript_revision_id,
            t_start_ms,
            t_end_ms,
            text,
            json.dumps(scores, sort_keys=True) if scores else None,
            json.dumps(flags, sort_keys=True) if flags else None,
            mutex_group_id,
            json.dumps(provenance, sort_keys=True) if provenance else None,
            _utc_iso(),
            _utc_iso(),
        ),
    )
    conn.commit()


def execution_kv_get(conn: sqlite3.Connection, key: str) -> Any | None:
    """Return the JSON-decoded value for ``key``, or ``None`` if absent."""
    cur = conn.execute("SELECT v_json FROM execution_kv WHERE k = ?", (key,))
    row = cur.fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def execution_kv_set(conn: sqlite3.Connection, key: str, value: Any) -> None:
    """Upsert a JSON-serializable value (scratch data only — never secrets)."""
    conn.execute(
        """
        INSERT INTO execution_kv (k, v_json, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(k) DO UPDATE SET v_json = excluded.v_json, updated_at = excluded.updated_at
        """,
        (key, json.dumps(value, sort_keys=True), _utc_iso()),
    )
    conn.commit()


def execution_kv_delete(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM execution_kv WHERE k = ?", (key,))
    conn.commit()
