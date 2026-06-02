from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

from interview_mux.file_store import lock_path_for


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
    with FileLock(lock_path_for(path)):
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    from interview_mux.process_logging import mirror_operator_entry

    mirror_operator_entry(entry)
    return entry


def read_log(run_dir: Path, *, tail: int | None = None) -> list[dict[str, Any]]:
    path = log_path(run_dir)
    if not path.is_file():
        return []
    with FileLock(lock_path_for(path)):
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
    if tail is not None and tail > 0:
        return entries[-tail:]
    return entries
