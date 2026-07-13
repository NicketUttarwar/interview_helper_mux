#!/usr/bin/env python3
"""Validate Flow 1 narrative QC for an execution."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.config import merged_config, repo_root  # noqa: E402
from interview_mux.edl_narrative_qc import validate_flow1_edl_narrative  # noqa: E402
from interview_mux.edl_qc import validate_flow1_edl  # noqa: E402
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
        description="Validate Flow 1 narrative QC, with optional EDL timeline/narrative checks."
    )
    parser.add_argument("--run-id", required=True, help="Execution id (e.g. exec_001 or run_201)")
    parser.add_argument(
        "--require-selection",
        action="store_true",
        help="Fail when master/selection.json is missing",
    )
    parser.add_argument(
        "--include-edl",
        action="store_true",
        help="Also run EDL timeline QC and final EDL narrative QC",
    )
    parser.add_argument(
        "--edl-narrative",
        action="store_true",
        help="Run final EDL narrative QC without timeline QC",
    )
    args = parser.parse_args()

    run_dir = _resolve_run_dir(args.run_id)
    if not run_dir.is_dir():
        print(f"Not found: {run_dir}")
        sys.exit(1)

    ctx = RunContext(args.run_id, create=False)
    groups: list[tuple[str, list[str]]] = [
        ("upstream narrative", validate_flow1_narrative(ctx, require_selection=args.require_selection))
    ]
    if args.include_edl:
        groups.append(("edl timeline", validate_flow1_edl(ctx)))
    if args.include_edl or args.edl_narrative:
        groups.append(("edl narrative", validate_flow1_edl_narrative(ctx)))

    failed = [(label, errors) for label, errors in groups if errors]
    if failed:
        print(f"FAIL: {run_dir}")
        for label, errors in failed:
            print(f"[{label}]")
            for err in errors:
                print(f"  - {err}")
        sys.exit(1)

    labels = ", ".join(label for label, _ in groups)
    print(f"OK: {run_dir} (Flow 1 QC passed: {labels})")
    sys.exit(0)


if __name__ == "__main__":
    main()
