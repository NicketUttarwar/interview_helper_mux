#!/usr/bin/env python3
"""Validate flow_1_master/edl.json for an execution (BUILD-067 boundary check)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.config import merged_config, repo_root  # noqa: E402
from interview_mux.prompt_validation import validate_edl_flow1  # noqa: E402


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
    parser = argparse.ArgumentParser(description="Validate flow_1_master/edl.json for a run.")
    parser.add_argument("--run-id", required=True, help="Execution id (e.g. exec_001_20260523T120000Z)")
    args = parser.parse_args()

    run_dir = _resolve_run_dir(args.run_id)
    edl_path = run_dir / "flow_1_master" / "edl.json"
    if not edl_path.is_file():
        print(f"Not found: {edl_path}")
        sys.exit(1)

    try:
        edl = json.loads(edl_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: {edl_path}")
        print(f"  invalid JSON: {exc}")
        sys.exit(1)

    if not isinstance(edl, dict):
        print(f"FAIL: {edl_path}")
        print("  expected a JSON object at root")
        sys.exit(1)

    errors = validate_edl_flow1(edl)
    if errors:
        print(f"FAIL: {edl_path}")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    clip_count = len(edl.get("clips") or [])
    print(f"OK: {edl_path} ({clip_count} clip(s), timeline {edl.get('timeline_duration_ms')} ms)")
    sys.exit(0)


if __name__ == "__main__":
    main()
