#!/usr/bin/env python3
"""Aggregate value-analysis spike scorecards (requires value_analysis.enabled + spike_scoring)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interview_mux.config import merged_config
from interview_mux.value_analysis.config import value_analysis_enabled
from interview_mux.value_analysis.spike_score import aggregate, load_scorecard


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate spike scorecard JSON.")
    parser.add_argument("--scorecard", required=True, help="Path to scorecard JSON")
    parser.add_argument(
        "--profiles",
        default="listener-first,idea-first",
        help="Comma-separated profile names",
    )
    parser.add_argument("--out", help="Write JSON or .md output path")
    args = parser.parse_args()

    cfg = merged_config()
    if not value_analysis_enabled(cfg):
        print("value_analysis.enabled is false — enable in config to run spike scoring.", file=sys.stderr)
        return 0

    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    scorecard = load_scorecard(args.scorecard)
    result = aggregate(scorecard, profiles, cfg=cfg)

    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        out_path = Path(args.out)
        if out_path.suffix.lower() == ".md":
            out_path.write_text(result.get("markdown", ""), encoding="utf-8")
        else:
            out_path.write_text(payload, encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print(payload)
        print("\n--- markdown ---\n")
        print(result.get("markdown", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
