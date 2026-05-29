"""Adjust VO bridge cues from measured vo_pickup WAV durations (BUILD-066 optional)."""

from __future__ import annotations

from typing import Any

from interview_mux.acoustic_profile import load_profile, placement_hints
from interview_mux.audio_timeline import wav_duration_ms
from interview_mux.prompt_validation import validate_sound_design_plan
from interview_mux.run_context import RunContext
from interview_mux.stages.assembly_flow1 import resolve_vo_pickup_path
from interview_mux.stages.sound_design_stages import _validate_sound_design_plan


def run_sound_design_vo_finalize(ctx: RunContext) -> None:
    sdp_path = "understanding/sound_design_plan.json"
    if not ctx.artifact_exists(sdp_path):
        ctx.log("vo_finalize: no sound_design_plan — skip", level="info", stage="sound_design_vo_finalize")
        ctx.mark_done("sound_design_vo_finalize")
        return

    plan = ctx.read_json(sdp_path)
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    flow1 = flow_plans.get("flow1") if isinstance(flow_plans.get("flow1"), dict) else {}
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

    errors = validate_sound_design_plan(plan)
    if errors:
        ctx.log(f"vo_finalize: SDP validation failed: {errors[:2]}", level="error", stage="sound_design_vo_finalize")
        raise SystemExit(f"sound_design_vo_finalize: invalid SDP after adjust: {errors[0]}")
    _validate_sound_design_plan(plan)
    ctx.write_json(sdp_path, plan)
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
