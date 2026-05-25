from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from filelock import FileLock


def lock_path_for(target: Path) -> Path:
    return target.parent / ".write.lock"


def read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    with FileLock(lock_path_for(path)):
        return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with FileLock(lock_path_for(path)):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)


def read_text(path: Path) -> str:
    with FileLock(lock_path_for(path)):
        return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(lock_path_for(path)):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
