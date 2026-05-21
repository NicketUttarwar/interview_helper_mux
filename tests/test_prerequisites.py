from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def test_check_prerequisites_script(repo_root: Path) -> None:
    script = repo_root / "tools" / "check_prerequisites.sh"
    if not script.is_file():
        return
    if not shutil.which("bash"):
        return
    proc = subprocess.run(["bash", str(script)], cwd=repo_root, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_verify_install_script(repo_root: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(repo_root / "tools" / "verify_install.py")],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_check_env_script(repo_root: Path) -> None:
    secrets = repo_root / "config" / "secrets" / "secrets.env"
    if not secrets.is_file():
        return
    proc = subprocess.run(
        [sys.executable, str(repo_root / "tools" / "check_env.py")],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
