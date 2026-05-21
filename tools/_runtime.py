"""Shared bootstrap for ``tools/*.py`` CLIs: use repo ``.venv`` and install deps if needed."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def repo_root_from_tools_file(tools_file: str | Path) -> Path:
    return Path(tools_file).resolve().parents[1]


def venv_python(repo_root: Path) -> Path | None:
    py = repo_root / ".venv" / "bin" / "python"
    return py if py.is_file() else None


def using_repo_venv(repo_root: Path) -> bool:
    """True when the active interpreter's prefix is this repo's ``.venv`` (not merely same binary path)."""
    venv_dir = (repo_root / ".venv").resolve()
    try:
        return Path(sys.prefix).resolve().is_relative_to(venv_dir)
    except ValueError:
        return str(Path(sys.prefix).resolve()).startswith(str(venv_dir))


def ensure_venv_interpreter(*, tools_file: str | Path) -> None:
    """Re-exec with ``.venv/bin/python`` when the repo venv exists and we are not already on it."""
    if os.environ.get("MUX_SKIP_VENV_REEXEC") == "1":
        return
    root = repo_root_from_tools_file(tools_file)
    vpy = venv_python(root)
    if vpy is None:
        return
    if using_repo_venv(root):
        return
    os.execv(str(vpy), [str(vpy), *sys.argv])


def ensure_project_installed(*, tools_file: str | Path) -> None:
    """Install editable project + dependencies into the active interpreter if imports are missing."""
    root = repo_root_from_tools_file(tools_file)
    vpy = venv_python(root)
    if vpy is not None and not using_repo_venv(root):
        raise SystemExit(
            f"Run with the repo virtualenv, not {sys.executable}:\n"
            f"  source .venv/bin/activate\n"
            f"  {vpy} tools/{Path(tools_file).name}"
        )
    req = root / "requirements.txt"
    missing: list[str] = []
    for mod in ("openai_mux", "pipeline", "openai"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if not missing:
        return
    print(
        f"Missing Python packages ({', '.join(missing)}). "
        f"Installing into {sys.executable} …",
        file=sys.stderr,
    )
    if not req.is_file():
        raise SystemExit(f"Missing {req}. Clone the full repository.")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req)])
    still: list[str] = []
    for mod in ("openai_mux", "pipeline", "openai"):
        try:
            __import__(mod)
        except ImportError:
            still.append(mod)
    if still:
        raise SystemExit(
            "Install failed. From the repo root with venv active, run:\n"
            "  pip install -r requirements.txt\n"
            "Or: ./scripts/bootstrap_venv.sh"
        )


def bootstrap(*, tools_file: str | Path) -> None:
    ensure_venv_interpreter(tools_file=tools_file)
    ensure_project_installed(tools_file=tools_file)
