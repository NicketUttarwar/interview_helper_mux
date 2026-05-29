#!/usr/bin/env python3
"""Validate Flow 1 narrative QC for an execution (coverage topics, non-empty chapters)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.config import merged_config, repo_root  # noqa: E402
from interview_mux.narrative_qc import validate_flow1_narrative  # noqa: E402
from interview_mux.run_context import RunContext  # noqa: E402


def _resolve_run_dir(run_id: str) -> Path:
    cfg = merged_config()
    executions_root = Path(cfg.get("executions_root", "ASSETS/executions"))
    if not executions_root.is_absolute():
        executions_root = repo_root() / executions_root
    legacy = repo_root() / cfg.get("data_root", "data") / run_id
    if legacy.is_dir():
        return legacy
    return executions_root / run_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Flow 1 narrative QC (topic coverage + selection chapters)."
    )
    parser.add_argument("--run-id", required=True, help="Execution id (e.g. exec_001 or run_201)")
    parser.add_argument(
        "--require-selection",
        action="store_true",
        help="Fail when flow_1_master/selection.json is missing",
    )
    args = parser.parse_args()

    run_dir = _resolve_run_dir(args.run_id)
    if not run_dir.is_dir():
        print(f"Not found: {run_dir}")
        sys.exit(1)

    ctx = RunContext(args.run_id, create=False)
    errors = validate_flow1_narrative(ctx, require_selection=args.require_selection)
    if errors:
        print(f"FAIL: {run_dir}")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"OK: {run_dir} (Flow 1 narrative QC passed)")
    sys.exit(0)


if __name__ == "__main__":
    main()
