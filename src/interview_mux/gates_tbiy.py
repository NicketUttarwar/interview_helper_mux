"""TBIY-specific gate checks (G1.5 preview pickup)."""

from __future__ import annotations

from datetime import datetime, timezone

from typing import Any

from interview_mux.config import merged_config
from interview_mux.production_profile import is_tbiy
from interview_mux.run_context import RunContext


def g1_5_preview_pickup_enabled() -> bool:
    cfg = merged_config().get("g1_5_preview_pickup") or {}
    return bool(cfg.get("enabled", True))


def post_preview_vo_satisfied(ctx: RunContext, line_id: str) -> bool:
    from interview_mux.vo_pickup_trim import get_line_metadata

    return bool(get_line_metadata(ctx, line_id).get("post_preview_recorded_at"))


def mark_post_preview_vo_recorded(ctx: RunContext, line_id: str) -> None:
    from interview_mux.vo_pickup_trim import load_vo_metadata, save_vo_metadata

    meta = load_vo_metadata(ctx)
    lines = meta.setdefault("lines", {})
    row = dict(lines.get(line_id) or {})
    row["post_preview_recorded_at"] = datetime.now(timezone.utc).isoformat()
    lines[line_id] = row
    save_vo_metadata(ctx, meta)


def check_g1_5_preview_pickup_pending(ctx: RunContext) -> list[str]:
    """Return line_ids needing record after preview listen (post_preview lines)."""
    return [row["line_id"] for row in list_g1_5_preview_pickup_lines(ctx) if not row.get("satisfied")]


def list_g1_5_preview_pickup_lines(ctx: RunContext) -> list[dict[str, Any]]:
    """Enriched post-preview pickup rows for GUI."""
    if not g1_5_preview_pickup_enabled() or not is_tbiy(ctx):
        return []
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not meta.get("preview_listened_at"):
        return []
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    report = ctx.read_json("understanding/gap_report.json")
    pickup = ctx.path("vo_pickup")
    rows: list[dict[str, Any]] = []
    for ln in report.get("interviewer_lines") or []:
        if not isinstance(ln, dict):
            continue
        if ln.get("delivery") != "record" or not ln.get("post_preview"):
            continue
        line_id = str(ln.get("line_id") or "")
        if not line_id:
            continue
        wav = pickup / f"{line_id}.wav"
        satisfied = wav.is_file() and post_preview_vo_satisfied(ctx, line_id)
        rows.append(
            {
                "line_id": line_id,
                "text": ln.get("text"),
                "gap_type": ln.get("gap_type"),
                "targets_segment_id": ln.get("targets_segment_id"),
                "voice_speaker_id": ln.get("voice_speaker_id"),
                "recorded_file": wav.name if wav.is_file() else None,
                "post_preview": True,
                "post_preview_satisfied": satisfied,
                "satisfied": satisfied,
            }
        )
    return rows


def require_g1_5_preview_pickup_clear(ctx: RunContext, *, stage: str) -> None:
    pending = check_g1_5_preview_pickup_pending(ctx)
    if pending:
        msg = (
            f"G1.5 preview pickup: record post-preview lines {pending[:6]} "
            f"→ {ctx.path('vo_pickup')}"
        )
        ctx.log(msg, level="warning", stage="g1_5_preview_pickup")
        raise SystemExit(msg)
