from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.file_store import write_lock


def log_path(run_dir: Path) -> Path:
    return run_dir / "gui_log.jsonl"


def _serialize_detail(detail: str | dict[str, Any] | None) -> str | None:
    if detail is None:
        return None
    if isinstance(detail, dict):
        return json.dumps(detail, ensure_ascii=False)
    return detail


def append_log(
    run_dir: Path,
    message: str,
    *,
    level: str = "info",
    stage: str | None = None,
    detail: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append to gui_log.jsonl. Levels: info, success, warning, error; action is GUI-only milestone."""
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
    }
    if stage:
        entry["stage"] = stage
    serialized = _serialize_detail(detail)
    if serialized:
        entry["detail"] = serialized
    path = log_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with write_lock(path):
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    from interview_mux.process_logging import mirror_operator_entry

    mirror_operator_entry(entry)
    return entry


def _read_tail_lines(path: Path, tail: int) -> list[str]:
    """Read last *tail* non-empty lines without loading the whole file."""
    if tail <= 0:
        return []
    chunk_size = 64 * 1024
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size == 0:
            return []
        data = b""
        pos = size
        while pos > 0 and data.count(b"\n") < tail:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            data = f.read(read_size) + data
        lines = data.splitlines()
        if not lines:
            return []
        selected = lines[-tail:] if len(lines) >= tail else lines
    return [ln.decode("utf-8", errors="replace").strip() for ln in selected if ln.strip()]


def read_log(
    run_dir: Path,
    *,
    tail: int | None = None,
    stage: str | None = None,
    since_ts: str | None = None,
) -> list[dict[str, Any]]:
    path = log_path(run_dir)
    if not path.is_file():
        return []
    with write_lock(path):
        if tail is not None and tail > 0 and not stage and not since_ts:
            raw_lines = _read_tail_lines(path, tail)
        else:
            raw_lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    entries: list[dict[str, Any]] = []
    for line in raw_lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if stage and entry.get("stage") != stage:
            continue
        if since_ts and str(entry.get("ts", "")) <= since_ts:
            continue
        entries.append(entry)
    if tail is not None and tail > 0 and (stage or since_ts):
        return entries[-tail:]
    return entries
