"""Deterministic post-generation placement QA — outputs adjustment hints for mix."""

from __future__ import annotations

import copy
import json
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

OUTPUT_PATH = "sound_design/placement_adjustments.json"


def placement_qa_enabled(cfg: dict[str, Any] | None = None) -> bool:
    c = cfg if cfg is not None else merged_config()
    return bool((c.get("sound_design") or {}).get("placement_qa_enabled", False))


def load_placement_adjustments(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(OUTPUT_PATH):
        return {"adjustments": []}
    doc = ctx.read_json(OUTPUT_PATH)
    return doc if isinstance(doc, dict) else {"adjustments": []}


def run_placement_qa(ctx: RunContext) -> dict[str, Any]:
    """
    Inspect generated assets vs SDP cues; emit conservative level/timing hints.
    Spectral analysis is optional v2 — v1 uses plan metadata + file presence.
    """
    adjustments: list[dict[str, Any]] = []
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return {"adjustments": adjustments, "version": 1}
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    assets_dir = ctx.path("sound_design", "assets")
    for asset in sdp.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        aid = str(asset.get("asset_id", ""))
        if not aid:
            continue
        wav = assets_dir / f"{aid}.wav"
        role = str(asset.get("role", ""))
        row: dict[str, Any] = {"asset_id": aid, "role": role}
        if not wav.is_file():
            row["action"] = "placeholder_silence"
            row["reason"] = "missing_wav"
            adjustments.append(row)
            continue
        try:
            size = wav.stat().st_size
            if size < 1000:
                row["action"] = "regenerate"
                row["reason"] = "suspiciously_small_wav"
                adjustments.append(row)
        except OSError:
            row["action"] = "regenerate"
            row["reason"] = "unreadable_wav"
            adjustments.append(row)
            continue
        if role == "ambient_bed":
            row["suggested_level_db_delta"] = -2.0
            row["reason"] = "default_speech_first_bed_lower"
            adjustments.append(row)
        elif role == "chapter_stinger":
            row["suggested_crossfade_ms"] = 120
            adjustments.append(row)
    doc = {"version": 1, "adjustments": adjustments}
    out = ctx.path(*OUTPUT_PATH.split("/"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    if adjustments:
        ctx.log(
            f"placement_qa: {len(adjustments)} adjustment hint(s) → {OUTPUT_PATH}",
            level="info",
            stage="mix_flow1",
        )
    return doc


def apply_placement_adjustments(
    ctx: RunContext,
    cues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply level/crossfade hints from placement_adjustments.json to cue copies."""
    doc = load_placement_adjustments(ctx)
    by_asset: dict[str, dict[str, Any]] = {}
    for row in doc.get("adjustments") or []:
        if isinstance(row, dict) and row.get("asset_id"):
            by_asset[str(row["asset_id"])] = row
    if not by_asset:
        return cues
    out: list[dict[str, Any]] = []
    level_applied = 0
    crossfade_applied = 0
    for cue in cues:
        if not isinstance(cue, dict):
            out.append(cue)
            continue
        cue_copy = copy.deepcopy(cue)
        aid = str(cue_copy.get("asset_id") or "")
        adj = by_asset.get(aid)
        if adj:
            delta = adj.get("suggested_level_db_delta")
            if delta is not None:
                cue_copy["level_db"] = float(cue_copy.get("level_db", -24.0)) + float(delta)
                level_applied += 1
            if adj.get("suggested_crossfade_ms") is not None:
                cue_copy["crossfade_ms"] = int(adj["suggested_crossfade_ms"])
                crossfade_applied += 1
        out.append(cue_copy)
    if level_applied or crossfade_applied:
        ctx.log(
            f"placement_qa: applied level to {level_applied} cue(s), crossfade to {crossfade_applied} cue(s)",
            level="info",
            stage="mix_flow1",
        )
    return out


def maybe_run_placement_qa(ctx: RunContext) -> None:
    if placement_qa_enabled():
        run_placement_qa(ctx)
