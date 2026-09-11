"""Adjust VO bridge cues from measured vo_pickup WAV durations (BUILD-066 optional)."""

from __future__ import annotations

from typing import Any

from interview_mux.acoustic_profile import load_profile, placement_hints
from interview_mux.audio_timeline import wav_duration_ms
from interview_mux.prompt_validation import validate_sound_design_plan
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import resolve_vo_pickup_path
from interview_mux.stages.sound_design_stages import _validate_sound_design_plan


def run_sound_design_vo_finalize(ctx: RunContext) -> None:
    try:
        from interview_mux.opening_adjacency_repair import (
            drop_late_intro_reset_from_selection,
            drop_orphan_opening_vo_when_native_orients,
            drop_post_coda_reverse_jump_from_selection,
            suppress_opening_layup_when_orientation_owns_slot,
        )

        suppress_opening_layup_when_orientation_owns_slot(ctx)
        drop_orphan_opening_vo_when_native_orients(ctx)
        drop_late_intro_reset_from_selection(ctx)
        drop_post_coda_reverse_jump_from_selection(ctx)
    except Exception as exc:  # noqa: BLE001 — bounded repair is fail-open
        ctx.log(
            f"opening_adjacency repair skipped: {exc}",
            level="warning",
            stage="sound_design_vo_finalize",
        )
    sdp_path = "understanding/sound_design_plan.json"
    if not ctx.artifact_exists(sdp_path):
        ctx.log("vo_finalize: no sound_design_plan — skip", level="info", stage="sound_design_vo_finalize")
        ctx.mark_done("sound_design_vo_finalize")
        return

    plan = ctx.read_json(sdp_path)
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    flow1 = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    cues = flow1.get("cues") if isinstance(flow1.get("cues"), list) else []
    assets = plan.get("assets") if isinstance(plan.get("assets"), list) else []
    assets_by_id = {
        str(a.get("asset_id")): a for a in assets if isinstance(a, dict) and a.get("asset_id")
    }

    gap_report: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/gap_report.json"):
        gap_report = ctx.read_json("understanding/gap_report.json")

    profile = load_profile(ctx)
    hints = placement_hints(profile)
    pre_roll = int(hints.get("vo_pre_roll_ms", 80))
    post_roll = int(hints.get("vo_post_roll_ms", 120))

    adjusted = 0
    skipped = 0
    missing_vo_bridge: list[str] = []
    with logged_step("sound_design_vo_finalize/adjust_cues", ctx=ctx, stage="sound_design_vo_finalize"):
        for cue in cues:
            if not isinstance(cue, dict):
                continue
            asset_id = str(cue.get("asset_id") or "")
            asset = assets_by_id.get(asset_id, {})
            role = str(asset.get("role") or cue.get("role") or "")
            line_id = str(cue.get("line_id") or cue.get("gap_line_id") or "")
            if role != "vo_bridge" and not line_id:
                continue
            line = _gap_line(gap_report, line_id)
            if line:
                wav = resolve_vo_pickup_path(ctx, line)
            else:
                wav = None
            if wav is None or not wav.is_file():
                skipped += 1
                # C-02: vo_bridge cues that need WAVs cannot hollow-complete finalize.
                if role == "vo_bridge" or line_id:
                    missing_vo_bridge.append(line_id or asset_id or "vo_bridge")
                continue
            dur = wav_duration_ms(wav)
            cue["measured_duration_ms"] = dur
            cue["pre_roll_ms"] = pre_roll
            cue["post_roll_ms"] = post_roll
            adjusted += 1

    if adjusted == 0 and skipped == 0:
        ctx.log("vo_finalize: no VO bridge cues to adjust — skip", level="info", stage="sound_design_vo_finalize")
        ctx.mark_done("sound_design_vo_finalize")
        return

    if missing_vo_bridge:
        ctx.log(
            f"vo_finalize: refuse mark_done — {len(missing_vo_bridge)} vo_bridge cue(s) lack WAVs",
            level="warning",
            stage="sound_design_vo_finalize",
            detail={"missing": missing_vo_bridge[:12]},
        )
        ctx.write_json(
            "mastering/sound_design_vo_finalize.json",
            {
                "skipped": False,
                "refused": True,
                "reason": "vo_bridge_cues_need_wavs",
                "missing": missing_vo_bridge[:24],
                "adjusted": adjusted,
                "skipped_cues": skipped,
            },
            skip_handoff=True,
            stage_key="sound_design_vo_finalize",
        )
        return

    errors = validate_sound_design_plan(plan)
    if errors:
        ctx.log(
            f"vo_finalize: SDP validation failed after adjust — leaving on-disk SDP: {errors[:2]}",
            level="warning",
            stage="sound_design_vo_finalize",
        )
        ctx.write_json(
            "mastering/sound_design_vo_finalize.json",
            {"skipped": True, "errors": [str(e) for e in errors[:6]]},
            skip_handoff=True,
            stage_key="sound_design_vo_finalize",
        )
        if adjusted:
            _patch_sonic_context_vo_bridges(ctx, plan)
        ctx.mark_done("sound_design_vo_finalize")
        return
    with logged_step("sound_design_vo_finalize/write", ctx=ctx, stage="sound_design_vo_finalize"):
        _validate_sound_design_plan(plan)
        ctx.write_json(sdp_path, plan)
        _patch_sonic_context_vo_bridges(ctx, plan)
    ctx.log(
        f"vo_finalize: adjusted={adjusted} skipped={skipped}",
        level="success",
        stage="sound_design_vo_finalize",
    )
    ctx.mark_done("sound_design_vo_finalize")


def _gap_line(gap_report: dict[str, Any], line_id: str) -> dict[str, Any] | None:
    if not line_id:
        return None
    for line in gap_report.get("interviewer_lines") or []:
        if isinstance(line, dict) and str(line.get("line_id") or "") == line_id:
            return line
    return None


def _patch_sonic_context_vo_bridges(ctx: RunContext, plan: dict[str, Any]) -> None:
    """Patch sonic_context vo_bridge cue opportunities with measured durations (fail-open)."""
    rel = "understanding/sonic_context.json"
    if not ctx.artifact_exists(rel):
        return
    doc = ctx.read_json(rel)
    if not isinstance(doc, dict):
        return
    flow1 = ((plan.get("flow_plans") or {}).get("podcast") or {})
    cues = flow1.get("cues") if isinstance(flow1.get("cues"), list) else []
    assets_by_id = {
        str(a.get("asset_id")): a
        for a in (plan.get("assets") or [])
        if isinstance(a, dict) and a.get("asset_id")
    }
    measured_by_segment: dict[str, dict[str, Any]] = {}
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        dur = cue.get("measured_duration_ms")
        if dur is None:
            continue
        seg = str(cue.get("segment_id") or cue.get("before_segment_id") or cue.get("after_segment_id") or "")
        asset_id = str(cue.get("asset_id") or "")
        asset = assets_by_id.get(asset_id, {})
        if str(asset.get("role") or "") != "vo_bridge" and not cue.get("line_id"):
            continue
        if seg:
            measured_by_segment[seg] = {
                "measured_duration_ms": int(dur),
                "asset_id": asset_id or None,
                "line_id": str(cue.get("line_id") or "") or None,
            }

    opportunities = doc.get("cue_opportunities") if isinstance(doc.get("cue_opportunities"), list) else []
    patched = 0
    for row in opportunities:
        if not isinstance(row, dict) or str(row.get("kind") or "") != "vo_bridge":
            continue
        seg = str(row.get("segment_id") or "")
        patch = measured_by_segment.get(seg)
        if not patch:
            continue
        row["measured_duration_ms"] = patch["measured_duration_ms"]
        if patch.get("asset_id"):
            row["asset_id"] = patch["asset_id"]
        if patch.get("line_id"):
            row["line_id"] = patch["line_id"]
        patched += 1
    if patched:
        from interview_mux.sonic_context import compute_sonic_context_hash

        doc["sonic_context_hash"] = compute_sonic_context_hash(doc)
        ctx.write_json(rel, doc)
        ctx.log(
            f"vo_finalize: patched {patched} vo_bridge cue_opportunit(ies) in sonic_context",
            level="info",
            stage="sound_design_vo_finalize",
        )
