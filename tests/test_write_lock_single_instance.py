"""Every ``.write.lock`` acquisition shares one lock instance per path (ISSUES 145).

filelock raises "Deadlock: lock ... is already held by a different FileLock
instance in this thread" when a second instance blocks on a path the same
thread already holds. ``file_store.write_lock`` is a per-path singleton, but the
session log, the action trace and the staging lock built their own instances
on the same ``.write.lock`` files, so a log line written while a write in that
folder held the lock stopped the run (client run: master/.write.lock,
SeedPrerequisiteFailed at 48/72).
"""

from __future__ import annotations

import re
from pathlib import Path

from interview_mux.file_store import write_lock

SRC = Path(__file__).resolve().parents[1] / "src" / "interview_mux"


def test_no_module_builds_its_own_write_lock_instance() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "file_store.py":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"FileLock\(\s*(?:str\()?\s*lock_path_for\(", text) or re.search(
            r"FileLock\([^)]*\.write\.lock", text
        ):
            offenders.append(str(path.relative_to(SRC)))
    assert offenders == []


def test_logging_while_the_folder_lock_is_held_does_not_deadlock(tmp_path: Path) -> None:
    from interview_mux.session_log import append_log

    with write_lock(tmp_path / "run_meta.json"):
        append_log(tmp_path, "inside a held run-root lock", level="info")
    assert "inside a held run-root lock" in (tmp_path / "gui_log.jsonl").read_text(encoding="utf-8")
