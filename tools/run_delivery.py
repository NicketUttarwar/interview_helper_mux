#!/usr/bin/env python3
"""Run delivery pipeline after analysis + G1 (single-flow)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.cli import delivery_cmd  # noqa: E402

if __name__ == "__main__":
    run_id = None
    from_stage = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--run-id" and i + 1 < len(args):
            run_id = args[i + 1]
            i += 2
        elif args[i] in ("--from-stage", "--delivery-from-stage", "--flow-from-stage") and i + 1 < len(args):
            from_stage = args[i + 1]
            i += 2
        elif args[i] == "--flow" and i + 1 < len(args):
            i += 2  # ignored — single delivery path
        else:
            i += 1
    delivery_cmd(run_id=run_id, from_stage=from_stage)
