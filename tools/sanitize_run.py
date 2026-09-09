#!/usr/bin/env python3
"""Wrapper: .venv/bin/python tools/sanitize_run.py → interview_mux.tools.sanitize_run."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from interview_mux.tools.sanitize_run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
