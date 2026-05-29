#!/usr/bin/env python3
"""Extract optional value_features.json for a run (off by default)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.value_analysis.config import value_analysis_enabled
from interview_mux.value_analysis.extract import extract_and_write_value_features
from interview_mux.value_analysis.features_transcript import VALUE_FEATURES_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract value features for a run.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--profile",
        choices=("transcript", "audio", "all"),
        default="all",
        help="Which feature profile to extract",
    )
    args = parser.parse_args()

    cfg = merged_config()
    if not value_analysis_enabled(cfg):
        print("value_analysis.enabled is false — no features extracted.", file=sys.stderr)
        return 0

    ctx = RunContext(args.run_id, create=False)
    if not ctx.run_dir.is_dir():
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 1

    if args.profile == "all":
        profiles = ("transcript", "audio")
    else:
        profiles = (args.profile,)

    written = extract_and_write_value_features(ctx, cfg=cfg, profiles=profiles)
    if not written:
        print("No profiles extracted (check value_analysis sub-flags).", file=sys.stderr)
        return 0

    print(f"Wrote {ctx.path(VALUE_FEATURES_PATH)} (profiles: {', '.join(written)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
