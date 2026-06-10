#!/usr/bin/env python3
"""Run disfluency_extract for a single execution."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from interview_mux.run_context import RunContext  # noqa: E402
from interview_mux.stages.disfluency import run_disfluency_extract  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    ctx = RunContext(args.run_id, create=False)
    run_disfluency_extract(ctx)
    print(f"Done — see {ctx.path('transcript/disfluencies.json')}")


if __name__ == "__main__":
    main()
