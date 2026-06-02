"""Post-flow artifact verification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def verify_flow(repo_root: Path, run_id: str, flow: str) -> tuple[bool, str]:
    run_dir = _resolve_run_dir(repo_root, run_id)
    if flow == "flow1":
        master = run_dir / "flow_1_master" / "master.wav"
        if not master.is_file():
            return False, f"Missing {master}"
        return _run_verify_master(repo_root, master, "flow1")
    if flow == "flow2":
        master = run_dir / "flow_2_highlights" / "master.wav"
        if not master.is_file():
            return False, f"Missing {master}"
        return _run_verify_master(repo_root, master, "flow2")
    if flow == "flow3":
        md = run_dir / "flow_3_description" / "show_description.md"
        if not md.is_file():
            return False, f"Missing {md}"
        proc = subprocess.run(
            [
                sys.executable,
                str(repo_root / "tools" / "validate_show_description.py"),
                "--run-id",
                run_id,
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return False, proc.stdout + proc.stderr
        return True, "show_description validated"
    return False, f"Unknown flow {flow}"


def _run_verify_master(repo_root: Path, master: Path, flow: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "verify_master.py"),
            str(master),
            "--flow",
            flow,
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False, proc.stdout + proc.stderr
    return True, proc.stdout.strip()


def _resolve_run_dir(repo_root: Path, run_id: str) -> Path:
    exec_dir = repo_root / "ASSETS" / "executions" / run_id
    if exec_dir.is_dir():
        return exec_dir
    legacy = repo_root / "data" / run_id
    return legacy
