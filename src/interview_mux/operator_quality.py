"""Preclean checkpoint registry and QC summary persistence on run_meta."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

PRECLEAN_CHECKPOINTS = frozenset(
    {
        "before_ingest",
        "after_g0",
        "after_profile_or_segmentation",
        "g1_vo_pickup",
        "before_sfx_spend",
        "before_flow_mix",
        "before_master_export",
    }
)

_STAGE_PRECLEAN_MAP: dict[str, str] = {
    "assembly_preview": "before_sfx_spend",
    "mix_flow1": "before_flow_mix",
    "mix_flow2": "before_flow_mix",
    "mux_flow1": "before_flow_mix",
    "mux_flow2": "before_flow_mix",
    "master_flow1": "before_master_export",
    "master_flow2": "before_master_export",
}


def preclean_acknowledged(meta: dict[str, Any], checkpoint: str) -> bool:
    preclean = meta.get("audio_preclean")
    if not isinstance(preclean, dict):
        return False
    offered = preclean.get("offered_at")
    if not isinstance(offered, list):
        return False
    return checkpoint in offered


def stage_requires_preclean_ack(stage_id: str) -> str | None:
    return _STAGE_PRECLEAN_MAP.get(stage_id)


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
