#!/usr/bin/env python3
"""CLI wrapper for backfill_volley_index."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from interview_mux.analysis_memory import CONTEXT_INDEX_PATH  # noqa: E402
from interview_mux.backfill_volley_index import backfill_volley_index  # noqa: E402
from interview_mux.context_resolver import (  # noqa: E402
    context_index_enabled,
    migrate_context_index_v1_to_v2,
)
from interview_mux.run_context import RunContext  # noqa: E402


def _run_dir(run_id: str) -> Path:
    root = REPO / "ASSETS" / "executions"
    matches = sorted(root.glob(f"{run_id}*"))
    if not matches:
        raise SystemExit(f"No run directory matching {run_id}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill volley memory index for a run")
    parser.add_argument("--run-id", required=True, help="Execution id prefix or full id")
    parser.add_argument("--dry-run", action="store_true", help="Count only; do not write")
    args = parser.parse_args()

    if not context_index_enabled():
        print("Note: context_index.enabled is false in config.")

    run_dir = _run_dir(args.run_id)
    ctx = RunContext(run_dir=run_dir, run_id=run_dir.name)
    raw = ctx.read_json(CONTEXT_INDEX_PATH) if ctx.artifact_exists(CONTEXT_INDEX_PATH) else {}
    migrated = migrate_context_index_v1_to_v2(raw, ctx.run_id)
    if not args.dry_run:
        ctx.write_json(CONTEXT_INDEX_PATH, migrated, skip_handoff=True)

    stats = backfill_volley_index(ctx, dry_run=args.dry_run)
    mode = "dry-run" if args.dry_run else "written"
    print(f"Backfill ({mode}) for {ctx.run_id}: {stats}")


if __name__ == "__main__":
    main()
