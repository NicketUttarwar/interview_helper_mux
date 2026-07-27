"""Simplified app configuration — single v2 pipeline."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config

ANALYSIS_ORDER: tuple[str, ...] = (
    "audio_preclean",
    "ingest",
    "transcribe",
    "transcript_review_build",
    "source_acoustic_profile",
    "interview_spine_build",
    "speaker_roles",
    "source_topology_build",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "content_brief_reanchor",
    "boundary_topic_resplit",
    "sonic_context_build",
    "sound_design_palettes",
    "missing_framing",
    "gap_framing_compose",
    "delivery_brief_build",
    "soundscape_policy_build",
    "episode_structure_compose",
)

DELIVERY_ORDER: tuple[str, ...] = (
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "refinement_agenda",  # confirm L0 after ranking
    "gap_framing_recompose",  # deterministic recompose/skip-copy — not an LLM call
    "selection_framing_apply",
    "ranking_refine",
    "narrative_arc_refine",
    "transitions",
    "transitions_refine",
    "sound_design_plan",
    "sdp_intent_refine",
    "sound_design_vo_finalize",
    "edl_narrative_audit",
    "edl_narrative_refine",
    "edl",
    "assembly_preview",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "mix",
    "master_finalize",
)

ALL_LLM_STAGES: frozenset[str] = frozenset(
    {
        "speaker_roles",
        "content_context",
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
        "boundary_topic_resplit",
        "sound_design_palettes",
        "missing_framing",
        "gap_framing_compose",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "transitions",
        "sound_design_plan",
        "sfx_prompt_craft",
        "edl_narrative_audit",
    }
)

# Backward-compatible aliases
ANALYSIS_ORDER_V2 = ANALYSIS_ORDER
DELIVERY_ORDER_V2 = DELIVERY_ORDER
ALL_LLM_STAGES_V2 = ALL_LLM_STAGES


def v2_cfg() -> dict[str, Any]:
    raw = merged_config().get("v2") or {}
    return raw if isinstance(raw, dict) else {}


def v2_auto_commit() -> bool:
    return bool(v2_cfg().get("auto_commit_artifacts", True))


def v2_g1_optional() -> bool:
    return bool(v2_cfg().get("g1_optional", True))


def effective_analysis_order() -> tuple[str, ...]:
    return ANALYSIS_ORDER


def effective_delivery_order() -> tuple[str, ...]:
    return DELIVERY_ORDER


# Deprecated stubs — always v2
def v2_enabled() -> bool:
    return True


def v2_skip_handoffs() -> bool:
    return True


def v2_skip_autopilot() -> bool:
    return True
