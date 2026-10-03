"""Structured action trace index — operator/action_trace.jsonl (forensics sidecar)."""

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from interview_mux.file_store import write_lock

ACTION_TRACE_REL = "operator/action_trace.jsonl"
TraceStatus = Literal["running", "ok", "error"]
TraceOrigin = Literal["gui", "api", "cli", "subprocess", "pipeline", "system"]

_active_trace_id: ContextVar[str | None] = ContextVar("active_trace_id", default=None)
_trace_stack: ContextVar[list[str]] = ContextVar("trace_stack", default=[])


def _trace_path(run_dir: Path) -> Path:
    return run_dir / ACTION_TRACE_REL


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_trace_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"act_{ts}_{uuid.uuid4().hex[:8]}"


def _append_line(run_dir: Path, record: dict[str, Any]) -> None:
    path = _trace_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with write_lock(path):
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    from interview_mux.operator_snapshots import record_action_trace_manifest

    record_action_trace_manifest(Path(run_dir))


def begin_action(
    action_id: str,
    *,
    run_dir: Path,
    stage: str | None = None,
    origin: TraceOrigin = "pipeline",
    summary: str | None = None,
    parent_trace_id: str | None = None,
    http: dict[str, Any] | None = None,
    command: list[str] | None = None,
    function: str | None = None,
    detail: dict[str, Any] | None = None,
) -> str:
    trace_id = _new_trace_id()
    parent = parent_trace_id or (_trace_stack.get()[-1] if _trace_stack.get() else None)
    record: dict[str, Any] = {
        "trace_id": trace_id,
        "ts_start": _now_iso(),
        "ts_end": None,
        "origin": origin,
        "action_id": action_id,
        "stage": stage,
        "status": "running",
        "summary": summary or action_id,
        "parent_trace_id": parent,
    }
    if http:
        record["http"] = http
    if command:
        record["command"] = command
    if function:
        record["function"] = function
    if detail:
        record["detail"] = detail
    _append_line(run_dir, record)
    stack = list(_trace_stack.get())
    stack.append(trace_id)
    _trace_stack.set(stack)
    _active_trace_id.set(trace_id)
    return trace_id


def end_action(
    trace_id: str,
    *,
    run_dir: Path,
    status: TraceStatus = "ok",
    detail: dict[str, Any] | None = None,
    follow_up: dict[str, Any] | None = None,
) -> None:
    record: dict[str, Any] = {
        "trace_id": trace_id,
        "ts_end": _now_iso(),
        "status": status,
        "event": "end",
    }
    if detail:
        record["detail"] = detail
    if follow_up:
        record["follow_up"] = follow_up
    _append_line(run_dir, record)
    stack = list(_trace_stack.get())
    if stack and stack[-1] == trace_id:
        stack.pop()
        _trace_stack.set(stack)
        _active_trace_id.set(stack[-1] if stack else None)


def read_action_trace(run_dir: Path, *, tail: int = 50) -> list[dict[str, Any]]:
    path = _trace_path(run_dir)
    if not path.is_file():
        return []
    with write_lock(path):
        lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if tail > 0:
        return entries[-tail:]
    return entries


def _collapse_trace(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for e in entries:
        tid = e.get("trace_id")
        if not tid:
            continue
        if tid not in by_id:
            by_id[tid] = dict(e)
        else:
            by_id[tid].update({k: v for k, v in e.items() if v is not None})
    return by_id


def format_dump_text(
    entries: list[dict[str, Any]],
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Normalized plain-text dump of recent completed actions."""
    collapsed = _collapse_trace(entries)
    completed = [
        v
        for v in collapsed.values()
        if v.get("status") in ("ok", "error", "running")
    ]
    completed.sort(key=lambda x: str(x.get("ts_start") or ""), reverse=True)
    lines: list[str] = []
    for rec in completed[:5]:
        aid = str(rec.get("action_id") or "?")
        desc = ""
        if catalog and aid in catalog:
            desc = str(catalog[aid].get("description") or "")
        lines.append("=== Operator action ===")
        lines.append(f"action_id:    {aid}")
        lines.append(f"stage:        {rec.get('stage') or '—'}")
        lines.append(f"status:       {rec.get('status') or '—'}")
        if desc:
            lines.append(f"description:  {desc}")
        if rec.get("function"):
            lines.append(f"function:     {rec['function']}")
        if rec.get("http"):
            http = rec["http"]
            lines.append(f"http:         {http.get('method', '?')} {http.get('path', '?')}")
        if rec.get("command"):
            cmd = rec["command"]
            if isinstance(cmd, list):
                lines.append(f"command:      {' '.join(str(c) for c in cmd)}")
        if rec.get("follow_up"):
            fu = rec["follow_up"]
            lines.append(f"follow_up:    {fu.get('action_id')} → {fu.get('stage', '')}")
        if rec.get("detail"):
            lines.append(f"detail:       {json.dumps(rec['detail'], ensure_ascii=False)}")
        lines.append(f"started:      {rec.get('ts_start') or '—'}")
        lines.append(f"ended:        {rec.get('ts_end') or '—'}")
        lines.append("---")
    return "\n".join(lines) if lines else "No action trace entries yet."


def active_trace_id() -> str | None:
    return _active_trace_id.get()
