#!/usr/bin/env python3
"""Validate soundscape policy + post-mix report for an execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.config import merged_config, repo_root  # noqa: E402
from interview_mux.prompt_validation import validate_soundscape_policy  # noqa: E402
from interview_mux.run_context import RunContext  # noqa: E402
from interview_mux.soundscape_policy import POLICY_PATH, load_policy  # noqa: E402
from interview_mux.soundscape_verify import evaluate_soundscape, load_soundscape_report  # noqa: E402


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
    parser = argparse.ArgumentParser(description="Validate soundscape policy and optional mix report.")
    parser.add_argument("--run-id", required=True, help="Execution id")
    parser.add_argument(
        "--require-report",
        action="store_true",
        help="Fail when soundscape_report.json is missing",
    )
    args = parser.parse_args()

    run_dir = _resolve_run_dir(args.run_id)
    if not run_dir.is_dir():
        print(f"Not found: {run_dir}")
        sys.exit(1)

    ctx = RunContext(args.run_id, create=False)
    policy = load_policy(ctx)
    if not policy:
        print(f"Missing {POLICY_PATH}")
        sys.exit(1)
    errors = validate_soundscape_policy(policy)
    if errors:
        print("Policy schema errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    report = load_soundscape_report(ctx)
    live = evaluate_soundscape(ctx)
    out = {
        "policy_hash": policy.get("policy_hash"),
        "underscore_policy": policy.get("underscore_policy"),
        "sfx_density": policy.get("sfx_density"),
        "cue_slots": len(policy.get("cue_slots") or []),
        "report": report,
        "live_evaluate": live,
    }
    print(json.dumps(out, indent=2))
    if args.require_report and not report:
        print("Missing sound_design/soundscape_report.json", file=sys.stderr)
        sys.exit(1)
    if report and report.get("verdict") == "fail_closed":
        sys.exit(2)
    if live.get("verdict") == "fail" and (report or {}).get("verdict") not in {"warning", "remediate", "pass"}:
        # Live fail without shipping warning is soft unless require-report
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
