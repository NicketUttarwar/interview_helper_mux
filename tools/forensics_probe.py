#!/usr/bin/env python3
"""Package forensics evidence for the parent agent — predicate, lies, and resume hints."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))


def _current_run_id(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    pointer = REPO / "ASSETS" / "full_auto_current_run.txt"
    if pointer.is_file():
        return pointer.read_text(encoding="utf-8").strip()
    raise SystemExit("No run_id — pass --run-id or launch full-auto first")


def _stage_done_lies(ctx) -> list[dict[str, Any]]:
    from interview_mux.stage_completion import (
        stage_artifact_incompleteness,
        stage_required_artifact_paths,
    )

    lies: list[dict[str, Any]] = []
    done_dir = ctx.run_dir / ".stage_done"
    if not done_dir.is_dir():
        return lies
    for marker in sorted(done_dir.iterdir()):
        if not marker.is_file():
            continue
        stage_id = marker.name
        missing = stage_artifact_incompleteness(ctx, stage_id)
        if missing:
            lies.append(
                {
                    "stage": stage_id,
                    "missing": missing,
                    "required": stage_required_artifact_paths(stage_id),
                }
            )
    return lies


def _order_drift(ctx) -> dict[str, Any] | None:
    try:
        from interview_mux.order_hash import edl_speech_clip_ids, order_drift_heal_action

        sel = ctx.read_json("master/selection.json") if ctx.artifact_exists("master/selection.json") else None
        edl = ctx.read_json("master/edl.json") if ctx.artifact_exists("master/edl.json") else None
        if not isinstance(sel, dict) or not isinstance(edl, dict):
            return None
        action = order_drift_heal_action(sel, edl)
        sel_ids = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
        clip_ids = edl_speech_clip_ids(edl)
        return {
            "heal_action": action,
            "selection_n": len(sel_ids),
            "clip_n": len(clip_ids),
            "clips_match_selection": clip_ids == sel_ids,
            "selection_tail": sel_ids[-5:],
            "clip_tail": clip_ids[-5:],
        }
    except Exception as exc:
        return {"error": str(exc)}


def _pending_writes(ctx) -> list[str]:
    pw = ctx.run_dir / ".pending_writes"
    if not pw.is_dir():
        return []
    return sorted(p.name for p in pw.iterdir() if p.is_dir() or p.is_file())


def _job_snapshot(run_id: str) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:8765/api/runs/{run_id}/job"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}


def build_probe(run_id: str) -> dict[str, Any]:
    from interview_mux.forensics_stall import read_escalation, read_stall
    from interview_mux.identical_failures import product_code_fingerprint, read_identical_failures
    from interview_mux.run_context import RunContext
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    ctx = RunContext(run_id, create=False)
    all_stages = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    done = [s for s in all_stages if ctx.is_done(s)]
    pending = [s for s in all_stages if not ctx.is_done(s)]
    job = _job_snapshot(run_id)
    stall = read_stall(ctx)
    escalation = read_escalation(ctx)
    identical = read_identical_failures(ctx)
    lies = _stage_done_lies(ctx)
    drift = _order_drift(ctx)

    producer_hint = ""
    if drift and drift.get("heal_action") == "rebuild":
        producer_hint = "run_edl"
    elif lies:
        producer_hint = str(lies[0].get("stage") or "")
    elif pending:
        producer_hint = pending[0]

    return {
        "version": 1,
        "run_id": run_id,
        "product_fingerprint": product_code_fingerprint(),
        "job": job,
        "progress": {
            "stages_done": len(done),
            "stages_total": len(all_stages),
            "first_pending": pending[0] if pending else None,
            "master_exists": ctx.artifact_exists("master/master.wav"),
        },
        "stall": stall,
        "escalation": escalation,
        "stage_done_lies": lies,
        "pending_writes": _pending_writes(ctx),
        "order_drift": drift,
        "identical_failures_halted": [
            row
            for row in (identical.get("signatures") or {}).values()
            if isinstance(row, dict) and row.get("halt")
        ],
        "recommended_resume": producer_hint,
        "parent_checklist": [
            "1. Identify predicate (file:function + failing field)",
            "2. Patch product code (producer stage, not downstream consumer)",
            "3. Add regression test asserting predicate flip",
            "4. pytest affected tests",
            "5. Restart driver: MUX_RUN_ID=<run_id> MUX_FRESH=0 MUX_FORENSICS=1",
            "6. Re-run this probe; confirm predicate_flipped before trusting progress",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Forensics evidence package for parent agent")
    parser.add_argument("--run-id", default=None, help="Run id (default: ASSETS/full_auto_current_run.txt)")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write operator/forensics_probe.json into the run directory",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only (default)")
    args = parser.parse_args()

    run_id = _current_run_id(args.run_id)
    probe = build_probe(run_id)

    if args.write:
        from interview_mux.run_context import RunContext

        RunContext(run_id, create=False).write_json("operator/forensics_probe.json", probe)

    print(json.dumps(probe, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
