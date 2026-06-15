#!/usr/bin/env python3
"""Verify MMAudio local venv and cloned repo."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from interview_mux.local_install import mmaudio_repo_dir  # noqa: E402
from interview_mux.local_runtime import resolve_venv_python  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--smoke-generate", action="store_true")
    args = parser.parse_args()

    py = resolve_venv_python("mmaudio")
    repo = mmaudio_repo_dir()
    script = ROOT / "tools" / "mmaudio_generate.py"
    proc = subprocess.run(
        [str(py), str(script), "--verify", "--repo", str(repo)]
        + (["--smoke-generate", "--work-dir", str(repo.parent)] if args.smoke_generate else []),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode
    print(proc.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
