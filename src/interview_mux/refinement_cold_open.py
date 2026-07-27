"""Optional cold-open + first-volley audition before synthesize-all."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def build_cold_open_audition(ctx: RunContext) -> dict[str, Any] | None:
    """Build a 20–40s cold-open audition plan when open/preface lines exist.

    Does not synthesize audio — writes a plan artifact for G1 UI / operator listen.
    """
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return None
    report = ctx.read_json("understanding/gap_report.json")
    if not isinstance(report, dict):
        return None
    lines = [ln for ln in (report.get("interviewer_lines") or []) if isinstance(ln, dict)]
    open_lines = [
        ln
        for ln in lines
        if str(ln.get("line_category") or "") in ("episode_preface", "cold_open")
        or ln.get("cold_open")
    ]
    if not open_lines:
        return None

    # Rough word→seconds at ~2.5 wps; clamp 20–40s window target
    texts = [str(ln.get("text") or ln.get("script") or "") for ln in open_lines]
    words = sum(len(t.split()) for t in texts)
    est_sec = words / 2.5
    payload = {
        "enabled": True,
        "line_ids": [str(ln.get("line_id") or "") for ln in open_lines if ln.get("line_id")],
        "estimated_seconds": round(est_sec, 1),
        "target_window_seconds": [20, 40],
        "within_window": 20 <= est_sec <= 40,
        "note": "Listen to cold open + first host beat before synthesize-all when open class activated",
        "producer": "refinement_cold_open",
    }
    ctx.write_json("understanding/cold_open_audition.json", payload)
    return payload
