from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

from interview_mux.file_store import lock_path_for


def log_path(run_dir: Path) -> Path:
    return run_dir / "gui_log.jsonl"


def append_log(run_dir: Path, message: str, *, level: str = "info", stage: str | None = None, detail: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
    }
    if stage:
        entry["stage"] = stage
    if detail:
        entry["detail"] = detail
    path = log_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with FileLock(lock_path_for(path)):
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
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
