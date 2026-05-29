#!/usr/bin/env python3
"""Validate segments/nle_edits.json for a run workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from interview_mux.prompt_validation import validate_nle_edits
from interview_mux.run_context import RunContext


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate NLE edits JSON for a run")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    ctx = RunContext(args.run_id, create=False)
    path = ctx.path("segments/nle_edits.json")
    if not path.is_file():
        print(f"Missing {path}")
        return 1
    data = ctx.read_json("segments/nle_edits.json")
    errors = validate_nle_edits(data if isinstance(data, dict) else {})
    if errors:
        for err in errors:
            print(err)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
