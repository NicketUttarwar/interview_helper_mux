from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from filelock import FileLock


def lock_path_for(target: Path) -> Path:
    return target.parent / ".write.lock"


def write_lock(target: Path) -> FileLock:
    """The directory write lock for ``target``, reentrant within a process.

    filelock creates a fresh instance per call, and since 3.13 it raises
    ``Deadlock`` when a second instance for the same path is acquired while
    another instance is held by the same thread. A run-root lock instance
    leaked inside the long-lived traversal process then failed every later
    write and every gate sign-off with that error. ``is_singleton=True`` is the
    library's documented remedy: one instance per path, with a reentrancy
    counter, so same-thread nesting or a stale handle cannot wedge the process.
    Cross-process exclusion is unchanged; it is still the OS lock.
    """
    return FileLock(str(lock_path_for(target)), is_singleton=True)


def read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    with write_lock(path):
        return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.name == "edl.json" and path.parent.name == "master" and isinstance(data, dict):
        try:
            from interview_mux.edl_source_contract import sanitize_edl_json_for_path

            data = sanitize_edl_json_for_path(path, data)
        except Exception:
            pass
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with write_lock(path):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)


def read_text(path: Path) -> str:
    with write_lock(path):
        return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with write_lock(path):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with write_lock(path):
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
    with write_lock(dest):
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
