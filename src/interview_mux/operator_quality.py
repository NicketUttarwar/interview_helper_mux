"""Preclean checkpoint registry and QC summary persistence on run_meta."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

PRECLEAN_CHECKPOINTS = frozenset(
    {
        "before_ingest",
        "g1_vo_pickup",
    }
)

OPTIONAL_PIPELINE_STAGES = frozenset({"audio_preclean"})


def preclean_checkpoint_decision(meta: dict[str, Any], checkpoint: str) -> str | None:
    """Return the latest operator decision for a checkpoint: accept, dismiss, or None."""
    preclean = meta.get("audio_preclean")
    if not isinstance(preclean, dict):
        return None
    decisions = preclean.get("decisions")
    if not isinstance(decisions, list):
        return None
    for row in reversed(decisions):
        if not isinstance(row, dict):
            continue
        if row.get("checkpoint") != checkpoint:
            continue
        action = str(row.get("action") or "").strip()
        if action in {"accept", "dismiss"}:
            return action
    return None


def preclean_acknowledged(meta: dict[str, Any], checkpoint: str) -> bool:
    preclean = meta.get("audio_preclean")
    if not isinstance(preclean, dict):
        return False
    offered = preclean.get("offered_at")
    if not isinstance(offered, list):
        return False
    return checkpoint in offered


def record_qc_summary(ctx: RunContext, key: str, payload: dict[str, Any]) -> None:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    summaries = meta.get("qc_summaries")
    if not isinstance(summaries, dict):
        summaries = {}
    entry = dict(payload)
    entry["recorded_at"] = datetime.now(timezone.utc).isoformat()
    summaries[key] = entry
    meta["qc_summaries"] = summaries
    ctx.write_json("run_meta.json", meta)


def qc_summary(meta: dict[str, Any], key: str) -> dict[str, Any] | None:
    summaries = meta.get("qc_summaries")
    if not isinstance(summaries, dict):
        return None
    row = summaries.get(key)
    return row if isinstance(row, dict) else None
