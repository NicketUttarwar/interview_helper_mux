#!/usr/bin/env python3
"""Run flow-specific pipeline after G2 (BUILD-051)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.cli import flow_cmd  # noqa: E402

if __name__ == "__main__":
    run_id = None
    from_stage = None
    flow = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--run-id" and i + 1 < len(args):
            run_id = args[i + 1]
            i += 2
        elif args[i] == "--from-stage" and i + 1 < len(args):
            from_stage = args[i + 1]
            i += 2
        elif args[i] == "--flow" and i + 1 < len(args):
            flow = args[i + 1]
            i += 2
        else:
            i += 1
    if not flow:
        print("Usage: python tools/run_flow.py --flow flow1|flow2|flow3 [--run-id run_001]")
        sys.exit(1)
    flow_cmd(flow=flow, run_id=run_id, from_stage=from_stage)
