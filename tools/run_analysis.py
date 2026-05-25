#!/usr/bin/env python3
"""Run shared analysis pipeline (BUILD-028)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.cli import analysis_cmd  # noqa: E402

if __name__ == "__main__":
    import typer

    run_id = None
    from_stage = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--run-id" and i + 1 < len(args):
            run_id = args[i + 1]
            i += 2
        elif args[i] == "--from-stage" and i + 1 < len(args):
            from_stage = args[i + 1]
            i += 2
        else:
            i += 1
    analysis_cmd(run_id=run_id, from_stage=from_stage)
