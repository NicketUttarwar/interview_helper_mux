"""Operator journey phase mapping and milestone computation."""

from __future__ import annotations

from typing import Any

from interview_mux.analysis_memory import ANALYSIS_STATE_PATH
from interview_mux.gates import (
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    get_selected_flow,
)
from interview_mux.g15_prompt_review import can_run_elevenlabs_generation
from interview_mux.config import merged_config
from interview_mux.run_context import RunContext


def _require_preview_listen() -> bool:
    cfg = merged_config().get("journey_ui")
    if isinstance(cfg, dict):
        return bool(cfg.get("require_preview_listen", False))
    return False

OPERATOR_PHASES = (
    "prepare",
    "understand",
    "complete",
    "create",
    "polish",
    "ship",
)

STAGE_TO_OPERATOR_PHASE: dict[str, str] = {
    "audio_preclean": "prepare",
    "ingest": "prepare",
    "transcribe": "prepare",
    "transcript_review_build": "prepare",
    "transcript_review": "prepare",
    "source_acoustic_profile": "understand",
    "speaker_roles": "understand",
    "content_context": "understand",
    "boundary_detection": "understand",
    "segment_classification": "understand",
    "content_brief_reanchor": "understand",
    "sound_design_palettes": "understand",
    "missing_framing": "understand",
    "optimal_questions": "understand",
    "analysis_profile": "understand",
    "g1_vo_pickup": "complete",
    "vo_ingest": "complete",
    "g2_flow_select": "complete",
    "topic_coverage_audit": "create",
    "narrative_arc_plan": "create",
    "full_master_ranking": "create",
    "transitions": "create",
    "sound_design_plan_flow1": "create",
    "sound_design_vo_finalize": "create",
    "edl_flow1": "create",
    "assembly_preview": "create",
    "highlight_selection": "create",
    "sound_design_plan_flow2": "create",
    "podcast_show_description": "create",
    "elevenlabs_prompt_craft": "polish",
    "elevenlabs_sfx_flow1": "polish",
    "elevenlabs_sfx_flow2": "polish",
    "mix_flow1": "polish",
    "mix_flow2": "polish",
    "export_show_description": "ship",
    "master_flow1": "ship",
    "master_flow2": "ship",
}


def stage_operator_phase(stage_id: str) -> str:
    return STAGE_TO_OPERATOR_PHASE.get(stage_id, "understand")


def read_run_meta(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists("run_meta.json"):
        return ctx.read_json("run_meta.json")
    return {}


def get_flow_intent(ctx: RunContext) -> str | None:
    meta = read_run_meta(ctx)
    intent = meta.get("flow_intent") or meta.get("selected_flow")
    if intent in ("flow1", "flow2", "flow3"):
        return intent
    return None


def get_selected_flow_meta(ctx: RunContext) -> str | None:
    return get_selected_flow(ctx)


def compute_milestones(ctx: RunContext) -> dict[str, bool]:
    meta = read_run_meta(ctx)
    stored = meta.get("journey_milestones")
    if isinstance(stored, dict):
        base = {k: bool(v) for k, v in stored.items()}
    else:
        base = {}

    tr_pending = check_transcript_review_pending(ctx)
    g0_complete = not tr_pending and ctx.is_done("transcript_review_build")
    if ctx.is_done("transcript_review") or (
        not tr_pending and ctx.artifact_exists("transcript/corrections.json")
    ):
        g0_complete = True

    profile_verified = False
    if ctx.artifact_exists(ANALYSIS_STATE_PATH):
        state = ctx.read_json(ANALYSIS_STATE_PATH)
        profile_verified = bool((state.get("meta") or {}).get("operator_verified"))

    g1_missing = check_g1_vo(ctx)
    g1_complete = not g1_missing and ctx.artifact_exists("analysis_complete.json")

    selected = get_selected_flow(ctx)
    g2_complete = selected in ("flow1", "flow2", "flow3")

    preview_ready = ctx.artifact_exists("flow_1_master/assembly_preview.wav")
    preview_listened = bool(meta.get("preview_listened_at"))

    sfx_approved = True
    ok, _ = can_run_elevenlabs_generation(ctx)
    if selected in ("flow1", "flow2"):
        sfx_approved = ok

    master_exported = (
        ctx.artifact_exists("flow_1_master/master.wav")
        or ctx.artifact_exists("flow_2_highlights/master.wav")
        or ctx.artifact_exists("flow_3_description/show_description.md")
    )

    computed = {
        "g0_complete": g0_complete,
        "profile_verified": profile_verified,
        "g1_complete": g1_complete,
        "g2_complete": g2_complete,
        "preview_ready": preview_ready,
        "preview_listened": preview_listened,
        "sfx_approved": sfx_approved,
        "master_exported": master_exported,
    }
    computed.update({k: v for k, v in base.items() if k in computed})
    return computed


def compute_operator_phase(ctx: RunContext, milestones: dict[str, bool] | None = None) -> str:
    ms = milestones or compute_milestones(ctx)
    flow = get_flow_intent(ctx) or get_selected_flow(ctx)

    if not ms.get("g0_complete"):
        return "prepare"
    if not ctx.artifact_exists("analysis_complete.json"):
        if not ms.get("profile_verified") and flow == "flow1":
            if ctx.is_done("content_context") or ctx.is_done("optimal_questions"):
                return "understand"
        if not ctx.is_done("optimal_questions"):
            return "understand"
    if not ms.get("g1_complete"):
        return "complete"
    if not ms.get("g2_complete"):
        return "complete"

    if flow == "flow3":
        if ctx.is_done("export_show_description"):
            return "ship"
        if ctx.is_done("podcast_show_description"):
            return "ship"
        return "create"

    if flow == "flow2":
        if ms.get("master_exported"):
            return "ship"
        if ctx.is_done("mix_flow2") or ctx.is_done("master_flow2"):
            return "ship"
        if ctx.is_done("elevenlabs_prompt_craft") or ctx.is_done("highlight_selection"):
            if ctx.is_done("highlight_selection") and not ctx.is_done("master_flow2"):
                return "polish"
        if ctx.is_done("highlight_selection"):
            return "polish"
        return "create"

    # flow1 default
    if ms.get("master_exported"):
        return "ship"
    if ctx.is_done("mix_flow1") or ctx.is_done("master_flow1"):
        return "ship"
    if ms.get("preview_ready") and not ctx.is_done("elevenlabs_sfx_flow1"):
        if ms.get("preview_listened") or not _require_preview_listen():
            return "polish"
        return "create"
    if ctx.is_done("assembly_preview"):
        return "create"
    if ms.get("g2_complete"):
        return "create"
    return "understand"
