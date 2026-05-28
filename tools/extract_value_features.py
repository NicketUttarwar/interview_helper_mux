#!/usr/bin/env python3
"""Extract optional value_features.json for a run (off by default)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.value_analysis.config import value_analysis_enabled
from interview_mux.value_analysis.features_audio import extract_audio_features
from interview_mux.value_analysis.features_transcript import (
    VALUE_FEATURES_PATH,
    extract_transcript_features,
)


def _load_existing(ctx: RunContext, run_id: str) -> dict[str, Any]:
    if ctx.artifact_exists(VALUE_FEATURES_PATH):
        data = ctx.read_json(VALUE_FEATURES_PATH)
        if isinstance(data, dict):
            return data
    return {"version": 1, "run_id": run_id, "profiles": {}}


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

    out = _load_existing(ctx, args.run_id)
    out["version"] = 1
    out["run_id"] = args.run_id
    profiles = out.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        out["profiles"] = profiles

    if args.profile in ("transcript", "all"):
        profiles["transcript"] = extract_transcript_features(ctx, cfg=cfg)
    if args.profile in ("audio", "all"):
        profiles["audio"] = extract_audio_features(ctx, cfg=cfg)

    ctx.write_json(VALUE_FEATURES_PATH, out)
    print(f"Wrote {ctx.path(VALUE_FEATURES_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
