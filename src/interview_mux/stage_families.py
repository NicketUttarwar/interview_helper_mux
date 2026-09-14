"""Stage-family adapters for the resilience runtime (all 69 pipeline stages)."""

from __future__ import annotations

from typing import Any

from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

# Family names used by stage_resilience / escalations / source recipes.
FAMILY_PREPARE = "prepare"
FAMILY_ANALYSIS = "analysis_shape"
FAMILY_FRAMING = "framing_g1"
FAMILY_SELECTION = "selection_edl"
FAMILY_SOUND = "sound_mix"
FAMILY_FINALIZE = "finalize_publish"

_PREPARE = frozenset(
    {
        "audio_preclean",
        "ingest",
        "transcribe",
        "audio_probe_build",
        "transcript_review_build",
    }
)
_FRAMING = frozenset(
    {
        "framing_posture_decide",
        "missing_framing",
        "mastering_plan_confirm",
        "gap_framing_compose",
        "gap_framing_recompose",
        "selection_framing_apply",
        "sound_design_vo_finalize",
        "vo_line_adjudicate",
    }
)
_SELECTION = frozenset(
    {
        "topic_coverage_audit",
        "narrative_arc_plan",
        "chapter_close_hitch",
        "connector_fuse_pass_pre_ranking",
        "full_master_ranking",
        "air_script_compose",
        "nugget_corpus_mine",
        "information_package_plan",
        "nugget_layup_compose",
        "refinement_agenda",
        "air_script_seams",
        "edl_narrative_audit",
        "vo_synthesize",
        "edl",
        "assembly_preview",
        "listen_delight_audit",
    }
)
_SOUND = frozenset(
    {
        "transitions",
        "sound_design_plan",
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "mix",
        "sonic_context_build",
        "sound_design_palettes",
        "soundscape_policy_build",
    }
)
_FINALIZE = frozenset(
    {
        "junction_snip_qa",
        "master_finalize",
        "master_transcript_build",
        "episode_meta_build",
        "episode_cover_prompt_craft",
        "podcast_encode_mp3",
        "episode_cover_generate",
        "podcast_publish",
    }
)

FAMILY_BY_STAGE: dict[str, str] = {}


def _build_registry() -> None:
    FAMILY_BY_STAGE.clear()
    for sid in ANALYSIS_ORDER + DELIVERY_ORDER:
        if sid in _PREPARE:
            FAMILY_BY_STAGE[sid] = FAMILY_PREPARE
        elif sid in _FRAMING:
            FAMILY_BY_STAGE[sid] = FAMILY_FRAMING
        elif sid in _SELECTION:
            FAMILY_BY_STAGE[sid] = FAMILY_SELECTION
        elif sid in _SOUND:
            FAMILY_BY_STAGE[sid] = FAMILY_SOUND
        elif sid in _FINALIZE:
            FAMILY_BY_STAGE[sid] = FAMILY_FINALIZE
        else:
            # Remaining analysis/shape stages
            FAMILY_BY_STAGE[sid] = FAMILY_ANALYSIS


_build_registry()

_FAMILY_REMEDIATION: dict[str, list[str]] = {
    FAMILY_PREPARE: [
        "source_profile_recipe",
        "stt_segmentize_from_words",
        "diarization_retry",
        "operator_escalate_g0",
    ],
    FAMILY_ANALYSIS: [
        "deterministic_fill",
        "bounded_llm_repair",
        "feasibility_gate",
        "operator_escalate",
    ],
    FAMILY_FRAMING: [
        "script_freeze",
        "ensure_g1_pickups",
        "skip_optional_vo",
        "operator_escalate",
    ],
    FAMILY_SELECTION: [
        "order_lock_enforce",
        "must_keep_force_slots",
        "layup_coverage_repair",
        "operator_escalate",
    ],
    FAMILY_SOUND: [
        "asset_job_ledger",
        "craft_duration_normalize",
        "mmaudio_qa_heal",
        "music_listen_escalate",
        "operator_escalate",
    ],
    FAMILY_FINALIZE: [
        "junction_remaster_budget",
        "pmq_repair_then_escalate",
        "loudnorm_retry",
        "cover_show_fallback",
        "s3_retry_escalate",
        "operator_escalate",
    ],
}


def family_for_stage(stage_id: str) -> str:
    return FAMILY_BY_STAGE.get(stage_id, FAMILY_ANALYSIS)


def remediation_for_stage(stage_id: str) -> list[str]:
    return list(_FAMILY_REMEDIATION.get(family_for_stage(stage_id), ["operator_escalate"]))


def default_escalation_options(stage_id: str) -> list[dict[str, Any]]:
    family = family_for_stage(stage_id)
    base: list[dict[str, Any]] = [
        {
            "id": "retry_stage",
            "label": f"Retry {stage_id} with preserved work",
            "resume_stage": stage_id,
            "safety": False,
        }
    ]
    if family == FAMILY_PREPARE:
        base.append(
            {
                "id": "open_g0_review",
                "label": "Open transcript review (G0)",
                "resume_stage": "transcript_review",
                "safety": True,
            }
        )
    elif family == FAMILY_FRAMING:
        base.extend(
            [
                {
                    "id": "retry_g1_synth",
                    "label": "Re-synthesize missing VO pickups",
                    "resume_stage": stage_id,
                    "safety": False,
                },
                {
                    "id": "skip_optional_vo",
                    "label": "Skip optional framing VO (documented)",
                    "resume_stage": stage_id,
                    "safety": False,
                },
            ]
        )
    elif family == FAMILY_SELECTION:
        base.append(
            {
                "id": "relock_selection",
                "label": "Commit a new selection order lock and rebuild EDL",
                "resume_stage": "full_master_ranking",
                "safety": False,
            }
        )
    elif family == FAMILY_SOUND:
        base.append(
            {
                "id": "resume_mix",
                "label": "Resume from mix after restoring assets/QA",
                "resume_stage": "mix",
                "safety": False,
            }
        )
    elif family == FAMILY_FINALIZE:
        base.extend(
            [
                {
                    "id": "retry_junction",
                    "label": "Retry junction remaster within budget",
                    "resume_stage": "junction_snip_qa",
                    "safety": False,
                },
                {
                    "id": "prepare_local_package_only",
                    "label": "Prepare local publish package (no S3)",
                    "resume_stage": "podcast_publish",
                    "safety": False,
                },
            ]
        )
    # Quality-first: never offer force_publish / soft_ship.
    return base


# Source-profile recipes selected after ingest (config/app.defaults.json resilience.source_profiles).
SOURCE_PROFILE_IDS = (
    "clean_interview",
    "town_hall_multi",
    "noisy_mono",
    "video_container",
    "short_source",
    "long_source",
)


def select_source_profile(
    *,
    speaker_count: int | None = None,
    duration_s: float | None = None,
    is_video: bool = False,
    noisy: bool = False,
) -> str:
    if is_video:
        return "video_container"
    if noisy:
        return "noisy_mono"
    if duration_s is not None and duration_s < 180:
        return "short_source"
    if duration_s is not None and duration_s > 7200:
        return "long_source"
    if speaker_count is not None and speaker_count >= 4:
        return "town_hall_multi"
    return "clean_interview"


def source_profile_recipe(profile_id: str) -> dict[str, Any]:
    """Documented knobs from config/app.defaults.json resilience.source_profiles."""
    from interview_mux.config import merged_config

    raw = ((merged_config().get("resilience") or {}).get("source_profiles") or {})
    row = raw.get(str(profile_id or "")) if isinstance(raw, dict) else None
    return dict(row) if isinstance(row, dict) else {}
