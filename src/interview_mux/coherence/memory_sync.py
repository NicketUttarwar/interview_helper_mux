from __future__ import annotations

from typing import Any

from interview_mux.analysis_memory import load_analysis_state, save_analysis_state
from interview_mux.coherence.config import int_threshold


def sync_coherence_to_state(ctx, report: dict[str, Any]) -> None:
    from interview_mux.coherence.config import coherence_cfg

    cfg = coherence_cfg()
    max_risks = int_threshold(cfg, "max_risks_in_memory", 20)
    state = load_analysis_state(ctx)
    open_risks = [
        {
            "risk_id": r.get("risk_id"),
            "kind": r.get("kind"),
            "time_ms": r.get("time_ms"),
            "window_id": r.get("window_id"),
            "theme_id": r.get("theme_id"),
            "claim_id": r.get("claim_id"),
            "confidence": r.get("confidence"),
            "blocking": bool(r.get("blocking", False)),
            "evidence": r.get("evidence") or {},
            "status": r.get("status", "open"),
        }
        for r in (report.get("risks") or [])
        if r.get("status", "open") == "open"
    ]
    state["coherence_risks"] = open_risks[:max_risks]
    save_analysis_state(ctx, state, stage="coherence")
