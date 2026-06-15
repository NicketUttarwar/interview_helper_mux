"""Deterministic post-generation placement QA — outputs adjustment hints for mix."""

from __future__ import annotations

import copy
import json
from typing import Any

from interview_mux.config import merged_config
from interview_mux.mmaudio_asset_qa import load_mmaudio_qa
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context

OUTPUT_PATH = "sound_design/placement_adjustments.json"


def placement_qa_enabled(cfg: dict[str, Any] | None = None) -> bool:
    c = cfg if cfg is not None else merged_config()
    return bool((c.get("sound_design") or {}).get("placement_qa_enabled", False))


def load_placement_adjustments(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(OUTPUT_PATH):
        return {"adjustments": []}
    doc = ctx.read_json(OUTPUT_PATH)
    return doc if isinstance(doc, dict) else {"adjustments": []}


def _mmaudio_qa_adjustments(ctx: RunContext) -> list[dict[str, Any]]:
    qa = load_mmaudio_qa(ctx)
    out: list[dict[str, Any]] = []
    for row in qa.get("assets") or []:
        if not isinstance(row, dict) or not row.get("asset_id"):
            continue
        aid = str(row["asset_id"])
        verdict = str(row.get("verdict") or "pass")
        if verdict == "pass" and not row.get("suggested_level_db_delta"):
            if row.get("suggested_crossfade_ms") is None:
                continue
        adj: dict[str, Any] = {
            "asset_id": aid,
            "role": row.get("role"),
            "mmaudio_qa_verdict": verdict,
            "provenance": {
                "rule_id": "mmaudio_qa",
                "source_artifact": "sound_design/mmaudio_qa.json",
                "detail": "Imported deterministic QA suggestion.",
            },
            "adaptive_level_source": "mmaudio_qa",
        }
        if row.get("reasons"):
            adj["reason"] = "; ".join(str(r) for r in row["reasons"])
        if row.get("action"):
            adj["action"] = row["action"]
        if row.get("suggested_level_db_delta") is not None:
            adj["suggested_level_db_delta"] = float(row["suggested_level_db_delta"])
        if row.get("suggested_crossfade_ms") is not None:
            adj["suggested_crossfade_ms"] = int(row["suggested_crossfade_ms"])
        if row.get("suggested_trim_ms") is not None:
            adj["suggested_trim_ms"] = int(row["suggested_trim_ms"])
        out.append(adj)
    return out


def run_placement_qa(ctx: RunContext) -> dict[str, Any]:
    """
    Inspect generated assets vs SDP cues; emit conservative level/timing hints.
    Merges mmaudio_qa.json when present.
    """
    adjustments: list[dict[str, Any]] = []
    mmaudio_adj = _mmaudio_qa_adjustments(ctx)
    by_asset = {str(a["asset_id"]): a for a in mmaudio_adj}

    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        doc = {"version": 1, "adjustments": mmaudio_adj}
        _write_placement_doc(ctx, doc)
        return doc

    sdp = ctx.read_json("understanding/sound_design_plan.json")
    sonic = load_sonic_context(ctx) or {}
    scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
    bucket = str(scenario.get("atlas_bucket") or "")
    flags = sonic.get("segment_flags") if isinstance(sonic.get("segment_flags"), dict) else {}
    overlap_high = {str(x) for x in (flags.get("overlap_high") or [])}
    trauma_adjacent = {str(x) for x in (flags.get("trauma_adjacent") or [])}
    flow1_cues = (
        ((sdp.get("flow_plans") or {}).get("flow1") or {}).get("cues") or []
        if isinstance(sdp, dict)
        else []
    )
    cue_by_asset: dict[str, dict[str, Any]] = {}
    for cue in flow1_cues:
        if isinstance(cue, dict) and cue.get("asset_id"):
            cue_by_asset[str(cue.get("asset_id"))] = cue
    assets_dir = ctx.path("sound_design", "assets")
    for asset in sdp.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        aid = str(asset.get("asset_id", ""))
        if not aid:
            continue
        if aid in by_asset:
            adjustments.append(by_asset[aid])
            continue
        wav = assets_dir / f"{aid}.wav"
        role = str(asset.get("role", ""))
        row: dict[str, Any] = {"asset_id": aid, "role": role}
        cue = cue_by_asset.get(aid) or {}
        if not wav.is_file():
            row["action"] = "placeholder_silence"
            row["reason"] = "missing_wav"
            row["provenance"] = {
                "rule_id": "asset_missing",
                "source_artifact": "sound_design/assets",
                "detail": "WAV missing for asset_id.",
            }
            row["adaptive_level_source"] = "default"
            adjustments.append(row)
            continue
        try:
            size = wav.stat().st_size
            if size < 1000:
                row["action"] = "regenerate"
                row["reason"] = "suspiciously_small_wav"
                row["provenance"] = {
                    "rule_id": "asset_small",
                    "source_artifact": "sound_design/assets",
                    "detail": "Generated WAV size below safe threshold.",
                }
                row["adaptive_level_source"] = "default"
                adjustments.append(row)
        except OSError:
            row["action"] = "regenerate"
            row["reason"] = "unreadable_wav"
            row["provenance"] = {
                "rule_id": "asset_unreadable",
                "source_artifact": "sound_design/assets",
                "detail": "Failed to stat/read generated WAV.",
            }
            row["adaptive_level_source"] = "default"
            adjustments.append(row)
            continue
        if role == "ambient_bed":
            row["suggested_level_db_delta"] = -2.0
            row["reason"] = "default_speech_first_bed_lower"
            row["provenance"] = {
                "rule_id": "ambient_default_lower",
                "source_artifact": "understanding/source_acoustic_profile.json",
                "detail": "Speech-first default bed ducking.",
            }
            row["adaptive_level_source"] = "sap_percentile"
            seg_id = str(cue.get("segment_id") or "")
            if seg_id and (seg_id in overlap_high or seg_id in trauma_adjacent):
                row["action"] = "skip"
                row["scenario_override"] = True
                row["reason"] = "scenario_segment_ban"
                row["provenance"] = {
                    "rule_id": "sonic_context_segment_ban",
                    "source_artifact": "understanding/sonic_context.json",
                    "detail": f"segment_id={seg_id} flagged overlap/trauma.",
                }
            elif bucket in {"panel", "trauma_adjacent", "noisy_room"}:
                row["suggested_level_db_delta"] = float(row["suggested_level_db_delta"]) - 2.0
                row["scenario_override"] = True
                row["provenance"] = {
                    "rule_id": "sonic_context_bucket_override",
                    "source_artifact": "understanding/sonic_context.json",
                    "detail": f"atlas_bucket={bucket}",
                }
            adjustments.append(row)
        elif role == "chapter_stinger":
            row["suggested_crossfade_ms"] = 120
            row["provenance"] = {
                "rule_id": "chapter_stinger_crossfade",
                "source_artifact": "sound_design/sound_design_plan.json",
                "detail": "Default chapter stinger smoothing.",
            }
            row["adaptive_level_source"] = "default"
            adjustments.append(row)

    for aid, adj in by_asset.items():
        if aid not in {a.get("asset_id") for a in adjustments}:
            adjustments.append(adj)

    doc = {"version": 1, "adjustments": adjustments}
    _write_placement_doc(ctx, doc)
    return doc


def _write_placement_doc(ctx: RunContext, doc: dict[str, Any]) -> None:
    out = ctx.path(*OUTPUT_PATH.split("/"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    adjustments = doc.get("adjustments") or []
    if adjustments:
        ctx.log(
            f"placement_qa: {len(adjustments)} adjustment hint(s) → {OUTPUT_PATH}",
            level="info",
            stage="mix_flow1",
        )


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
            if str(adj.get("action") or "") == "skip":
                cue_copy["skip"] = True
            delta = adj.get("suggested_level_db_delta")
            if delta is not None:
                cue_copy["level_db"] = float(cue_copy.get("level_db", -24.0)) + float(delta)
                level_applied += 1
            if adj.get("suggested_crossfade_ms") is not None:
                cue_copy["crossfade_ms"] = int(adj["suggested_crossfade_ms"])
                crossfade_applied += 1
            if adj.get("suggested_trim_ms") is not None:
                cue_copy["trim_tail_ms"] = int(adj["suggested_trim_ms"])
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
