from __future__ import annotations

from typing import Any

from interview_mux.coherence.config import int_threshold


def coherence_investigations(report: dict[str, Any]) -> list[dict[str, Any]]:
    from interview_mux.config import merged_config

    cfg = merged_config().get("coherence") or {}
    max_items = int_threshold(cfg, "max_investigations_per_run", 8)
    risks = [r for r in report.get("risks") or [] if r.get("status", "open") == "open"]
    items: list[dict[str, Any]] = []

    for risk in sorted(risks, key=lambda r: (-float(r.get("confidence") or 0), r.get("kind") or "")):
        kind = str(risk.get("kind") or "")
        if kind not in ("topic_drift", "claim_contradiction", "missing_callback"):
            continue
        action = risk.get("suggested_action") or {}
        stage = str(action.get("stage") or _default_stage(kind))
        time_s = int(risk.get("time_ms") or 0) // 1000
        question = _question_for(kind, time_s, risk)
        priority = _priority_for(kind, risk)
        target: dict[str, Any] = {
            "risk_id": risk.get("risk_id"),
        }
        if risk.get("window_id"):
            target["window_id"] = risk.get("window_id")
        if risk.get("time_ms") is not None:
            target["start_ms"] = risk.get("time_ms")
        if risk.get("theme_id"):
            target["theme_id"] = risk.get("theme_id")
        if risk.get("claim_id"):
            target["claim_id"] = risk.get("claim_id")
        items.append(
            {
                "kind": kind,
                "priority": priority,
                "blocking": bool(risk.get("blocking", False)),
                "question": question,
                "target": target,
                "evidence": risk.get("evidence") or {},
                "suggested_action": {"type": "rerun_stage", "stage": stage},
            }
        )
        if len(items) >= max_items:
            break
    return items


def _default_stage(kind: str) -> str:
    if kind == "missing_callback":
        return "topic_coverage_audit"
    return "content_brief_reanchor"


def _priority_for(kind: str, risk: dict[str, Any]) -> str:
    if risk.get("blocking"):
        return "high"
    if kind == "claim_contradiction":
        return "medium"
    return "low"


def _question_for(kind: str, time_s: int, risk: dict[str, Any]) -> str:
    if kind == "topic_drift":
        return f"Topic drift near {time_s}s — confirm brief themes still cover this section."
    if kind == "claim_contradiction":
        claim = (risk.get("evidence") or {}).get("claim_text") or risk.get("claim_id") or "claim"
        return f"Possible contradiction near {time_s}s vs earlier claim: {str(claim)[:120]}"
    topic = (risk.get("evidence") or {}).get("topic") or risk.get("theme_id") or "topic"
    return f"Missing callback for '{topic}' in second half — verify coverage or arc plan."
