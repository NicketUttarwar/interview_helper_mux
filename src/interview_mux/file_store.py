from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

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


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(lock_path_for(path)):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)


def atomic_copy(
    src: Path,
    dest: Path,
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """Promote src to dest via tmp + replace under dest lock (streaming copy)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = src.stat().st_size if src.is_file() else 0
    with FileLock(lock_path_for(dest)):
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        if on_progress and total > 0:
            copied = 0
            chunk = 1 << 20
            with src.open("rb") as fin, tmp.open("wb") as fout:
                while True:
                    block = fin.read(chunk)
                    if not block:
                        break
                    fout.write(block)
                    copied += len(block)
                    on_progress(copied, total)
        else:
            shutil.copyfile(src, tmp)
        tmp.replace(dest)


def atomic_copy_tree(src_root: Path, dest_root: Path) -> list[str]:
    """Copy all files under src_root into dest_root; return relative paths copied."""
    copied: list[str] = []
    if not src_root.is_dir():
        return copied
    for src in sorted(src_root.rglob("*")):
        if not src.is_file() or src.name.endswith(".lock"):
            continue
        rel = str(src.relative_to(src_root)).replace("\\", "/")
        dest = dest_root.joinpath(*rel.split("/"))
        atomic_copy(src, dest)
        copied.append(rel)
    return copied
