"""Operator journey phase mapping and milestone computation."""

from __future__ import annotations

from typing import Any

from interview_mux.analysis_memory import ANALYSIS_STATE_PATH
from interview_mux.gates import (
    check_disfluency_review_pending,
    check_g1_vo,
    check_transcript_review_pending,
)
from interview_mux.sfx_prompt_review import can_run_sfx_generation
from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context


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
    "disfluency_extract": "prepare",
    "disfluency_review": "prepare",
    "source_acoustic_profile": "understand",
    "interview_spine_build": "understand",
    "speaker_roles": "understand",
    "content_context": "understand",
    "boundary_detection": "understand",
    "segment_classification": "understand",
    "content_brief_reanchor": "understand",
    "boundary_topic_resplit": "understand",
    "sound_design_palettes": "understand",
    "missing_framing": "understand",
    "gap_framing_compose": "understand",
    "optimal_questions": "understand",
    "analysis_profile": "understand",
    "g1_vo_pickup": "complete",
    "vo_ingest": "complete",
    "topic_coverage_audit": "create",
    "narrative_arc_plan": "create",
    "full_master_ranking": "create",
    "transitions": "create",
    "sound_design_plan": "create",
    "sound_design_vo_finalize": "create",
    "edl_narrative_audit": "create",
    "edl": "create",
    "assembly_preview": "create",
    "g1_5_preview_pickup": "polish",
    "sfx_prompt_craft": "polish",
    "mmaudio_sfx": "polish",
    "mix": "polish",
    "mux_flow1": "polish",
    "podcast_sfx_brief": "polish",
    "master_finalize": "ship",
}


def stage_operator_phase(stage_id: str) -> str:
    return STAGE_TO_OPERATOR_PHASE.get(stage_id, "understand")


def read_run_meta(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists("run_meta.json"):
        return ctx.read_json("run_meta.json")
    return {}


def _post_listen_gate_active() -> bool:
    sound_cfg = merged_config().get("sound_design") or {}
    mode = str(sound_cfg.get("post_listen_gate_mode", "warn")).lower()
    return mode in {"block", "block_mix"}


def _compute_sfx_generated(ctx: RunContext) -> bool:
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return False
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict) and a.get("asset_id")]
    if not assets:
        return False
    if not ctx.is_done("mmaudio_sfx"):
        return False
    for asset in assets:
        aid = str(asset.get("asset_id"))
        if not ctx.artifact_exists(f"sound_design/assets/{aid}.wav"):
            return False
    return True


def _compute_sfx_listen_complete(ctx: RunContext) -> bool:
    if not _post_listen_gate_active():
        return True
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return True
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    asset_ids = [
        str(a.get("asset_id"))
        for a in (sdp.get("assets") or [])
        if isinstance(a, dict) and a.get("asset_id")
    ]
    if not asset_ids:
        return True
    meta = read_run_meta(ctx)
    listen = meta.get("sfx_listen_results") or []
    latest: dict[str, str] = {}
    for row in listen:
        if isinstance(row, dict) and row.get("asset_id"):
            latest[str(row.get("asset_id"))] = str(row.get("result") or "")
    for aid in asset_ids:
        if latest.get(aid) != "pass":
            return False
    return True


def get_flow_intent(ctx: RunContext) -> str | None:
    """Legacy flow intent from run_meta (ignored — single delivery path)."""
    meta = read_run_meta(ctx)
    intent = meta.get("flow_intent")
    if intent in ("flow1", "podcast", "delivery"):
        return "podcast"
    return None


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

    disfluency_complete = ctx.is_done("disfluency_review") or not check_disfluency_review_pending(ctx)

    profile_verified = False
    if ctx.artifact_exists(ANALYSIS_STATE_PATH):
        state = ctx.read_json(ANALYSIS_STATE_PATH)
        profile_verified = bool((state.get("meta") or {}).get("operator_verified"))

    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

    g1_missing = check_g1_vo(ctx)
    if gap_fill_was_skipped(ctx):
        g1_complete = ctx.artifact_exists("analysis_complete.json")
    else:
        g1_complete = not g1_missing and ctx.artifact_exists("analysis_complete.json")

    preview_ready = ctx.artifact_exists("master/assembly_preview.wav")
    preview_listened = bool(meta.get("preview_listened_at"))

    from interview_mux.gates_tbiy import check_g1_5_preview_pickup_pending

    g1_5_preview_pickup_complete = not check_g1_5_preview_pickup_pending(ctx)

    sfx_approved = True
    ok, _ = can_run_sfx_generation(ctx)
    sfx_approved = ok

    master_exported = ctx.artifact_exists("master/master.wav")

    computed = {
        "g0_complete": g0_complete,
        "disfluency_complete": disfluency_complete,
        "profile_verified": profile_verified,
        "g1_complete": g1_complete,
        "preview_ready": preview_ready,
        "preview_listened": preview_listened,
        "g1_5_preview_pickup_complete": g1_5_preview_pickup_complete,
        "sfx_approved": sfx_approved,
        "sonic_context_ready": bool(load_sonic_context(ctx)),
        "sfx_generated": _compute_sfx_generated(ctx),
        "sfx_listen_complete": _compute_sfx_listen_complete(ctx),
        "placement_qa_ready": ctx.artifact_exists("sound_design/placement_adjustments.json"),
        "master_exported": master_exported,
    }
    for key, stored_val in base.items():
        if key not in computed:
            computed[key] = stored_val
            continue
        if isinstance(stored_val, bool) and isinstance(computed.get(key), bool):
            computed[key] = bool(computed[key] or stored_val)
    return computed


def compute_operator_phase(ctx: RunContext, milestones: dict[str, bool] | None = None) -> str:
    ms = milestones or compute_milestones(ctx)

    if not ms.get("g0_complete"):
        return "prepare"
    if not ctx.artifact_exists("analysis_complete.json"):
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
        from interview_mux.pipeline import shared_analysis_chain_complete
        from interview_mux.stages import gaps

        if gap_fill_was_skipped(ctx) and shared_analysis_chain_complete(ctx):
            if not ms.get("profile_verified"):
                return "understand"
        else:
            if not ms.get("profile_verified"):
                if ctx.is_done("content_context") or gaps.gap_compose_stage_done(ctx):
                    return "understand"
            if not gaps.gap_compose_stage_done(ctx):
                return "understand"
    if not ms.get("g1_complete"):
        return "complete"

    if ms.get("master_exported"):
        return "ship"
    if ctx.is_done("mix") or ctx.is_done("master_finalize"):
        return "ship"
    if ms.get("preview_ready") and not ctx.is_done("mmaudio_sfx"):
        if ms.get("preview_listened") or not _require_preview_listen():
            return "polish"
        return "create"
    if ctx.is_done("assembly_preview"):
        return "create"
    if ms.get("g1_complete"):
        return "create"
    return "understand"
