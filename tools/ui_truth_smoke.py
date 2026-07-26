#!/usr/bin/env python3
"""Walk run snapshots and fail on UI truth invariant violations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.config import merged_config, repo_root  # noqa: E402
from interview_mux.run_context import RunContext  # noqa: E402
from interview_mux.ui_truth import validate_run_snapshot  # noqa: E402
from interview_mux.gates import (  # noqa: E402
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    is_operator_profile_verified,
)
from interview_mux.web.server import _build_stage_list  # noqa: E402


def _executions_dir() -> Path:
    cfg = merged_config()
    return repo_root() / cfg.get("assets_root", "ASSETS") / cfg.get("executions_root", "ASSETS/executions").split("/", 1)[-1]


def audit_run(run_id: str) -> list[str]:
    if not RunContext.exists(run_id):
        return [f"{run_id}: not found"]
    ctx = RunContext(run_id, create=False)
    stages = _build_stage_list(
        ctx,
        check_g1_vo(ctx),
        check_transcript_review_pending(ctx),
        is_operator_profile_verified(ctx),
        check_profile_gate_pending(ctx),
    )
    journey = None
    try:
        from interview_mux.web.server import build_journey_snapshot

        journey = build_journey_snapshot(ctx)
    except Exception:
        journey = {}
    job = None
    job_path = ctx.path("gui_job.json")
    if job_path.is_file():
        import json

        job = json.loads(job_path.read_text(encoding="utf-8"))
    analysis_state = None
    context_index = None
    try:
        analysis_state = ctx.read_json("understanding/analysis_state.json")
    except Exception:
        analysis_state = None
    try:
        context_index = ctx.read_json("understanding/context_index.json")
    except Exception:
        context_index = None
    violations = validate_run_snapshot(
        stages=stages,
        journey=journey,
        job=job,
        analysis_state=analysis_state,
        context_index=context_index,
    )
    return [f"{run_id} [{v.code}] {v.message}" for v in violations]


def main() -> int:
    parser = argparse.ArgumentParser(description="UI truth smoke — invariant checks per run")
    parser.add_argument("--run-id", help="Single exec_* id (default: all under executions/)")
    args = parser.parse_args()
    exec_dir = repo_root() / merged_config().get("executions_root", "ASSETS/executions")
    run_ids = [args.run_id] if args.run_id else sorted(
        p.name for p in exec_dir.iterdir() if p.is_dir() and p.name.startswith("exec_")
    )
    if not run_ids:
        print("No executions to audit.")
        return 0
    failures: list[str] = []
    for rid in run_ids:
        failures.extend(audit_run(rid))
    if failures:
        print("UI truth smoke FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"OK — {len(run_ids)} run(s) passed UI truth invariants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
