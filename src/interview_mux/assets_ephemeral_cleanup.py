"""Fresh-launch cleanup for ephemeral paths under ASSETS/.

INVARIANT — stage execution reuse must never break:
  At every pipeline stage the GUI looks back at up to
  ``journey_ui.stage_reuse_lookback_executions`` (default 5) prior
  product ``exec_*`` folders, matches ``source_audio_hash``, and offers
  to copy stage outputs. Those folders (``.stage_done/``, ``run_meta.json``,
  and all stage artifacts under each ``exec_*``) are durable and are
  **never** deleted or rewritten by this module.

Durable (never deleted by launch cleanup):
  - Operator source audio under ASSETS/ (and ASSETS/input/)
  - Local ML runtimes: ASSETS/local_* (venvs, models, hf_cache, cloned repos)
  - Pipeline workspaces: ASSETS/executions/exec_* matching EXEC_ID_RE
    (including all stage outputs used by stage_execution_reuse)
  - ASSETS/executions/.execution_counter

Ephemeral (cleared on ./scripts/run.sh by default):
  - ASSETS/.gui session pointer files (unless MUX_PRESERVE_SESSION=1)
  - ASSETS/.gui/sessions/* (operator session bootstrap logs)
  - Orphan dirs under executions/ that are not product exec_* folders
    (pytest / tooling debris such as accept_*, cv_*, run_chunk_*)
  - Stale process locks only: ``.run.lock`` and top-level ``.write.lock``
    under product exec_* (never artifact files)
  - Empty ``.pending_writes/`` trees (non-empty staging is left intact)

Pipeline stage outputs live only under RunContext.run_dir (exec_*).
OS temp dirs used by STT/MMAudio are cleaned by those callers, not here.
"""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root
from interview_mux.run_context import EXEC_ID_RE

_GUI_SESSION_FILES = (
    "application_state.json",
    "active_execution.json",
    "server_session.json",
    "api_consent.json",
    "active_execution.json.lock",
    "server_session.json.lock",
    "api_consent.json.lock",
)

_KEEP_EXECUTIONS_FILES = frozenset(
    {
        ".execution_counter",
        ".execution_counter.lock",
        ".gitkeep",
    }
)

# Only these names may be removed from inside a product exec_* folder.
_EPHEMERAL_INSIDE_EXEC = frozenset({".run.lock", ".write.lock"})


@dataclass
class CleanupReport:
    cleared_gui_session_files: list[str] = field(default_factory=list)
    removed_operator_sessions: int = 0
    removed_orphan_execution_dirs: list[str] = field(default_factory=list)
    removed_stale_locks: list[str] = field(default_factory=list)
    removed_empty_pending_writes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cleared_gui_session_files": list(self.cleared_gui_session_files),
            "removed_operator_sessions": self.removed_operator_sessions,
            "removed_orphan_execution_dirs": list(self.removed_orphan_execution_dirs),
            "removed_stale_locks": list(self.removed_stale_locks),
            "removed_empty_pending_writes": list(self.removed_empty_pending_writes),
        }


def assets_root(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or merged_config()
    return repo_root() / cfg.get("assets_root", "ASSETS")


def executions_root(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or merged_config()
    rel = cfg.get("executions_root", "ASSETS/executions")
    p = Path(rel)
    return p if p.is_absolute() else repo_root() / p


def gui_dir(cfg: dict[str, Any] | None = None) -> Path:
    return assets_root(cfg) / ".gui"


def is_product_execution_dir(name: str) -> bool:
    """True for durable pipeline runs that participate in stage-reuse lookback."""
    return bool(EXEC_ID_RE.match(name))


def _unlink(path: Path) -> bool:
    if not path.is_file() and not path.is_symlink():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def _rmtree(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        shutil.rmtree(path)
        return True
    except OSError:
        return False


def _is_empty_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        next(path.iterdir())
    except StopIteration:
        return True
    except OSError:
        return False
    return False


def _clear_gui_session_files(root: Path, report: CleanupReport) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in _GUI_SESSION_FILES:
        path = root / name
        if _unlink(path):
            report.cleared_gui_session_files.append(name)


def _clear_operator_session_logs(root: Path, report: CleanupReport) -> None:
    sessions = root / "sessions"
    if not sessions.is_dir():
        return
    for child in list(sessions.iterdir()):
        if child.is_dir():
            if _rmtree(child):
                report.removed_operator_sessions += 1
        elif _unlink(child):
            report.removed_operator_sessions += 1


def _clear_gui_lock_files(root: Path, report: CleanupReport) -> None:
    if not root.is_dir():
        return
    for path in root.glob("*.lock"):
        if _unlink(path):
            report.removed_stale_locks.append(path.name)


def _clear_orphan_execution_dirs(exec_root: Path, report: CleanupReport) -> None:
    """Remove non-product debris under executions/. Never touches EXEC_ID_RE dirs."""
    if not exec_root.is_dir():
        return
    for child in list(exec_root.iterdir()):
        if child.name in _KEEP_EXECUTIONS_FILES:
            continue
        if child.name == ".DS_Store":
            _unlink(child)
            continue
        if child.is_dir() and is_product_execution_dir(child.name):
            continue
        if child.is_dir():
            if _rmtree(child):
                report.removed_orphan_execution_dirs.append(child.name)
        elif child.is_file() and child.name.endswith(".lock"):
            if child.name not in _KEEP_EXECUTIONS_FILES and _unlink(child):
                report.removed_stale_locks.append(child.name)


def _clear_ephemeral_inside_product_execs(exec_root: Path, report: CleanupReport) -> None:
    """Strip process locks / empty staging only — never stage outputs or .stage_done."""
    if not exec_root.is_dir():
        return
    for child in list(exec_root.iterdir()):
        if not child.is_dir() or not is_product_execution_dir(child.name):
            continue
        for name in _EPHEMERAL_INSIDE_EXEC:
            lock = child / name
            if _unlink(lock):
                report.removed_stale_locks.append(f"{child.name}/{name}")
        pending = child / ".pending_writes"
        if not pending.is_dir():
            continue
        for stage_dir in list(pending.iterdir()):
            if stage_dir.is_dir() and _is_empty_dir(stage_dir):
                _rmtree(stage_dir)
        if _is_empty_dir(pending) and _rmtree(pending):
            report.removed_empty_pending_writes.append(child.name)


def cleanup_ephemeral_assets(
    *,
    clear_gui_session: bool = True,
    cfg: dict[str, Any] | None = None,
) -> CleanupReport:
    """Remove launch-ephemeral files under ASSETS/.

    Never deletes product ``exec_*`` workspaces or their stage outputs — required
    for the 5-execution stage-reuse lookback at every pipeline stage.
    """
    report = CleanupReport()
    gdir = gui_dir(cfg)
    exec_root = executions_root(cfg)

    if clear_gui_session:
        _clear_gui_session_files(gdir, report)
    _clear_operator_session_logs(gdir, report)
    _clear_gui_lock_files(gdir, report)
    _clear_orphan_execution_dirs(exec_root, report)
    _clear_ephemeral_inside_product_execs(exec_root, report)
    return report


def clear_gui_session_files_only(*, fresh: bool = False, cfg: dict[str, Any] | None = None) -> None:
    """Backward-compatible helper used by application_session.clear_session_files."""
    if not fresh:
        return
    report = CleanupReport()
    _clear_gui_session_files(gui_dir(cfg), report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clear ephemeral ASSETS/ paths for a fresh launch")
    parser.add_argument(
        "--preserve-session",
        action="store_true",
        help="Keep .gui application_state / legacy session pointer files",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress summary line")
    args = parser.parse_args(argv)

    preserve = args.preserve_session or os.environ.get("MUX_PRESERVE_SESSION", "0") == "1"
    report = cleanup_ephemeral_assets(clear_gui_session=not preserve)
    if not args.quiet:
        orphans = len(report.removed_orphan_execution_dirs)
        print(
            "assets ephemeral cleanup: "
            f"gui_files={len(report.cleared_gui_session_files)} "
            f"sessions={report.removed_operator_sessions} "
            f"orphan_exec_dirs={orphans} "
            f"locks={len(report.removed_stale_locks)} "
            f"empty_pending={len(report.removed_empty_pending_writes)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
