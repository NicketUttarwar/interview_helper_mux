from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from interview_mux.run_context import RunContext


def check_transcript_review_pending(ctx: RunContext) -> bool:
    """True when STT review queue exists but operator has not signed off."""
    if ctx.is_done("transcript_review"):
        return False
    return ctx.artifact_exists("transcript/review_queue.json")


def require_transcript_review_clear(ctx: RunContext) -> None:
    if check_transcript_review_pending(ctx):
        raise SystemExit(
            "Transcript review gate: open the GUI, listen to ranked clips, correct text, "
            f"then mark review complete → {ctx.path('transcript/review_queue.json')}"
        )


def check_g1_vo(ctx: RunContext) -> list[str]:
    """Return list of missing line_ids for delivery=record."""
    report_path = ctx.path("understanding", "gap_report.json")
    if not report_path.is_file():
        return []
    report = ctx.read_json("understanding/gap_report.json")
    pickup = ctx.path("vo_pickup")
    missing: list[str] = []
    for line in report.get("interviewer_lines") or []:
        if line.get("delivery") != "record":
            continue
        lid = line.get("line_id", "")
        seg = line.get("targets_segment_id", "")
        candidates = [pickup / f"{lid}.wav", pickup / f"{seg}.wav"]
        if not any(p.is_file() for p in candidates):
            missing.append(lid or seg)
    return missing


def require_g1_clear(ctx: RunContext) -> None:
    missing = check_g1_vo(ctx)
    if missing:
        raise SystemExit(
            f"G1 gate: record VO for {missing} → {ctx.path('vo_pickup')}\n"
            f"See {ctx.path('understanding', 'interviewer_script.txt')}"
        )


def set_selected_flow(ctx: RunContext, flow: str) -> None:
    if flow not in ("flow1", "flow2"):
        raise ValueError("flow must be flow1 or flow2")
    meta = {
        "selected_flow": flow,
        "selected_at": datetime.now(timezone.utc).isoformat(),
    }
    ctx.write_json("run_meta.json", meta)


def get_selected_flow(ctx: RunContext) -> str | None:
    p = ctx.path("run_meta.json")
    if not p.is_file():
        return None
    return ctx.read_json("run_meta.json").get("selected_flow")
