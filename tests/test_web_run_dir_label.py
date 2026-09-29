"""The job API's run_dir label survives an executions_root outside the repo (ISSUES 77)."""

from __future__ import annotations

from pathlib import Path

from interview_mux.web.server import _run_dir_label


def test_run_dir_inside_repo_is_relative(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    run_dir = root / "ASSETS" / "executions" / "exec_001"
    assert _run_dir_label(run_dir, root) == str(Path("ASSETS") / "executions" / "exec_001")


def test_run_dir_outside_repo_is_absolute_not_a_crash(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    run_dir = tmp_path / "elsewhere" / "executions" / "exec_001"
    assert _run_dir_label(run_dir, root) == str(run_dir)
