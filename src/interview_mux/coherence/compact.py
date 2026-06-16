from __future__ import annotations

from typing import Any

from interview_mux.coherence.config import coherence_active
from interview_mux.coherence.duration_gate import coherence_activated
from interview_mux.coherence.paths import COHERENCE_REPORT_PATH


_STAGE_CAPS: dict[str, int] = {
    "topic_coverage_audit": 5,
    "narrative_arc_plan": 4,
    "content_brief_reanchor": 4,
    "missing_framing": 3,
    "podcast_show_description": 2,
}


def compact_for_volley(ctx, stage_key: str) -> dict[str, Any] | None:
    if not coherence_active() or not coherence_activated(ctx):
        return None
    if not ctx.artifact_exists(COHERENCE_REPORT_PATH):
        return None
    report = ctx.read_json(COHERENCE_REPORT_PATH)
    if not isinstance(report, dict):
        return None

    cap = _STAGE_CAPS.get(stage_key, 3)
    risks = [r for r in report.get("risks") or [] if r.get("status", "open") == "open"]

    if stage_key == "podcast_show_description":
        risks = [r for r in risks if r.get("kind") == "claim_contradiction" and r.get("blocking")]

    compact_risks = []
    for r in risks[:cap]:
        compact_risks.append(
            {
                "kind": r.get("kind"),
                "time_ms": r.get("time_ms"),
                "confidence": r.get("confidence"),
                "theme_id": r.get("theme_id"),
                "claim_id": r.get("claim_id"),
                "evidence": {
                    k: v
                    for k, v in (r.get("evidence") or {}).items()
                    if k in ("drift_score", "novelty_score", "theme_alignment", "topic", "claim_text")
                },
            }
        )

    summary = report.get("summary") or {}
    return {
        "activated": True,
        "summary": {
            "topic_drift_count": summary.get("topic_drift_count", 0),
            "claim_contradiction_count": summary.get("claim_contradiction_count", 0),
            "missing_callback_count": summary.get("missing_callback_count", 0),
        },
        "risks": compact_risks,
    }


def attach_coherence_summary(payload: dict[str, Any], ctx, stage_key: str) -> dict[str, Any]:
    summary = compact_for_volley(ctx, stage_key)
    if summary:
        payload["coherence_summary"] = summary
    return payload
