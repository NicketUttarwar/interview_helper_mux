"""Flow integrity — skip-copy draft to final; G1 always reachable."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

SKIP_COPY_REL = "understanding/refinement_skip_copy.json"
DRAFT_REL = "understanding/gap_report.draft.json"
FINAL_REL = "understanding/gap_report.json"


def _empty_report() -> dict[str, Any]:
    return {
        "interviewer_lines": [],
        "gaps": [],
        "_meta": {"producer": "refinement_flow_integrity", "producer_stage": "skip_copy"},
    }


def skip_copy_draft_to_final(ctx: RunContext, *, reason: str = "pass2_skipped") -> dict[str, Any]:
    """Promote draft (or empty) to authoritative gap_report so G1/delivery never dead-end."""
    if ctx.artifact_exists(DRAFT_REL):
        draft = ctx.read_json(DRAFT_REL)
        report = draft if isinstance(draft, dict) else _empty_report()
    elif ctx.artifact_exists(FINAL_REL):
        report = ctx.read_json(FINAL_REL)
        if not isinstance(report, dict):
            report = _empty_report()
    else:
        report = _empty_report()

    # Dual-write draft if missing (stamp selection hash for adopt freshness).
    if not ctx.artifact_exists(DRAFT_REL) and isinstance(report, dict):
        draft_out = dict(report)
        dmeta = (
            dict(draft_out.get("_meta") or {})
            if isinstance(draft_out.get("_meta"), dict)
            else {}
        )
        try:
            if ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                if isinstance(sel, dict):
                    h = str(sel.get("order_content_hash") or "").strip()
                    if h:
                        dmeta["selection_order_content_hash"] = h
                        draft_out["selection_order_content_hash"] = h
        except Exception:
            pass
        if dmeta:
            draft_out["_meta"] = dmeta
        ctx.write_json(DRAFT_REL, draft_out)

    ctx.write_json(FINAL_REL, report)
    marker = {
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "line_count": len(report.get("interviewer_lines") or []),
    }
    ctx.write_json(SKIP_COPY_REL, marker)
    ctx.log(
        f"Skip-copy draft→final gap_report ({reason})",
        level="info",
        stage="gap_framing_recompose",
        action_id="refinement_skip_copy",
        detail=marker,
    )
    return report


def ensure_gap_report_authoritative(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists(FINAL_REL):
        doc = ctx.read_json(FINAL_REL)
        if isinstance(doc, dict):
            return doc
    return skip_copy_draft_to_final(ctx, reason="ensure_authoritative")


def g1_reachable(ctx: RunContext) -> bool:
    """G1 is reachable whenever authoritative report exists (possibly empty lines)."""
    ensure_gap_report_authoritative(ctx)
    return True


def dual_write_draft_from_compose(ctx: RunContext) -> None:
    """After compose, snapshot draft alongside final (stamp selection hash for freshness)."""
    if not ctx.artifact_exists(FINAL_REL):
        return
    report = ctx.read_json(FINAL_REL)
    if not isinstance(report, dict):
        return
    out = dict(report)
    meta = dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
    try:
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                h = str(sel.get("order_content_hash") or "").strip()
                if h:
                    meta["selection_order_content_hash"] = h
                    out["selection_order_content_hash"] = h
    except Exception:
        pass
    if meta:
        out["_meta"] = meta
    ctx.write_json(DRAFT_REL, out)
