"""Simplified app configuration — single v2 pipeline."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config

ANALYSIS_ORDER: tuple[str, ...] = (
    "audio_preclean",
    "ingest",
    "transcribe",
    "audio_probe_build",
    "transcript_review_build",
    "source_acoustic_profile",
    "interview_spine_build",
    "speaker_roles",
    "source_topology_build",
    "content_context",
    "talking_points_compose",
    "ideal_cuts_propose",
    "ideal_cuts_materialize",
    "boundary_detection",
    "segment_classification",
    "content_brief_reanchor",
    "framing_posture_decide",
    "boundary_topic_resplit",
    "vernacular_segment_sanitize",
    "low_conf_island_scan",
    "connector_fuse_pass",
    "sonic_context_build",
    "sound_design_palettes",
    "mastering_research_routing",
    "mastering_research_waves",
    "mastering_research_rollup",
    "mastering_shape_agenda",
    "mastering_shape_candidates",
    "mastering_plan_synthesize",
    "missing_framing",
    "mastering_plan_confirm",
    "gap_framing_compose",
    "delivery_brief_build",
    "soundscape_policy_build",
    "episode_structure_compose",
)

DELIVERY_ORDER: tuple[str, ...] = (
    "topic_coverage_audit",
    "narrative_arc_plan",
    "chapter_close_hitch",
    "connector_fuse_pass_pre_ranking",
    "full_master_ranking",
    "air_script_compose",
    # Nugget Layup System: full-tape mine → per-native before-VO (authoritative gap_report).
    "nugget_corpus_mine",
    "information_package_plan",
    "nugget_layup_compose",
    # Slim Pass-2: agenda + gap recompose + framing apply only (no-op *_refine removed).
    "refinement_agenda",
    "gap_framing_recompose",
    "selection_framing_apply",
    "air_script_seams",
    "transitions",
    "sound_design_plan",
    "sound_design_vo_finalize",
    "vo_line_adjudicate",
    "vo_synthesize",
    "edl_narrative_audit",
    "edl",
    "assembly_preview",
    "listen_delight_audit",
    "music_palette_compose",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "mix",
    "junction_snip_qa",
    "master_finalize",
    "master_transcript_build",
    "episode_meta_build",
    "episode_cover_prompt_craft",
    "podcast_encode_mp3",
    "episode_cover_generate",
    "podcast_publish",
)

# Post-master ship stages. Homunculus 0.1.0 walks these after master.wav exists
# even when the conductor does not call walk_seed_remainder (cover / RSS / S3).
SHIP_AFTER_MASTER: tuple[str, ...] = (
    "master_transcript_build",
    "episode_meta_build",
    "episode_cover_prompt_craft",
    "podcast_encode_mp3",
    "episode_cover_generate",
    "podcast_publish",
)

ALL_LLM_STAGES: frozenset[str] = frozenset(
    {
        # LLM-capable stages (many skip LLM when talking-points / ideal-cuts authority applies).
        "speaker_roles",
        "content_context",
        "talking_points_compose",
        "ideal_cuts_propose",
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
        "framing_posture_decide",
        "boundary_topic_resplit",
        "connector_seam_adjudicate",
        "sound_design_palettes",
        "missing_framing",
        "gap_framing_compose",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "nugget_corpus_mine",
        "nugget_layup_compose",
        "synthetic_framing_plan",
        "transitions",
        "sound_design_plan",
        "sfx_prompt_craft",
        "music_palette_compose",
        "edl_narrative_audit",
        "vo_line_adjudicate",
        "episode_meta_build",
        "episode_cover_prompt_craft",
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
