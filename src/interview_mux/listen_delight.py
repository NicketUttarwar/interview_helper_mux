"""Advisory listen delight audit — never blocks master_finalize."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.mastering_plan_loader import best_available_mode, load_plan_raw
from interview_mux.narrative_mode import mode_consistency_report
from interview_mux.run_context import RunContext

AUDIT_REL = "mastering/listen_delight_audit.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_listen_delight_audit(ctx: RunContext) -> None:
    plan = load_plan_raw(ctx) or {}
    mode = best_available_mode(plan) if plan else "sparse_source"
    lines: list[dict[str, Any]] = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        gr = ctx.read_json("understanding/gap_report.json")
        if isinstance(gr, dict):
            raw = gr.get("interviewer_lines") or []
            if isinstance(raw, list):
                lines = [x for x in raw if isinstance(x, dict)]
    consistency = mode_consistency_report(mode=mode, interviewer_lines=lines, plan=plan or None)
    # Advisory scores only
    finishability = 0.7 if consistency.get("ok") else 0.55
    recommendability = 0.65 if lines or mode == "sparse_source" else 0.5
    audit = {
        "version": 1,
        "advisory": True,
        "blocking": False,
        "narrative_mode": mode,
        "finishability": finishability,
        "fatigue_risk": 0.3,
        "mode_audible": True,
        "recommendability": recommendability,
        "mode_consistency": consistency,
        "notes": [
            "Listen delight is always advisory and must not block master_finalize",
        ],
        "human_rubric_ref": "NORTH_STAR.md#human-listen-rubric-operational-delight-check",
        "generated_at": _now(),
    }
    ctx.write_json(AUDIT_REL, audit)
    # Surface in run_meta.qc_summaries without blocking
    meta: dict[str, Any]
    if ctx.artifact_exists("run_meta.json"):
        doc = ctx.read_json("run_meta.json")
        meta = doc if isinstance(doc, dict) else {}
    else:
        meta = {}
    qc = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
    qc["listen_delight"] = {
        "advisory": True,
        "blocking": False,
        "finishability": finishability,
        "recommendability": recommendability,
        "mode_consistency_ok": consistency.get("ok"),
    }
    qc["mode_consistency"] = {
        "advisory": True,
        "blocking": False,
        "ok": consistency.get("ok"),
        "violations": consistency.get("violations"),
    }
    meta["qc_summaries"] = qc
    ctx.write_json("run_meta.json", meta)
