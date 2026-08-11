"""Ten-phase operator journey for v2 simplified workbench."""

from __future__ import annotations

from typing import Any

PHASES: list[dict[str, Any]] = [
    {
        "id": "start",
        "label": "Start",
        "description": "Select interview audio; optional background-noise pre-clean offer.",
        "stages": [],
        "gate": None,
    },
    {
        "id": "prepare",
        "label": "Prepare",
        "description": "Normalize audio, transcribe, build transcript review queue.",
        "stages": [
            "audio_preclean",
            "ingest",
            "transcribe",
            "audio_probe_build",
            "transcript_review_build",
        ],
        "gate": None,
    },
    {
        "id": "fix_transcript",
        "label": "Fix transcript",
        "description": "Correct STT errors before analysis (mandatory).",
        "stages": [],
        "gate": "transcript_review",
    },
    {
        "id": "understand",
        "label": "Understand",
        "description": "Speakers, talking-points cuts, segments, research + Shape plan.",
        "stages": [
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
        ],
        "gate": None,
    },
    {
        "id": "fill_gaps",
        "label": "Fill gaps",
        "description": "Optional: interviewer framing VO (summaries, prefaces, questions) or skip.",
        "stages": [
            "missing_framing",
            "mastering_plan_confirm",
            "gap_framing_compose",
            "delivery_brief_build",
            "soundscape_policy_build",
            "episode_structure_compose",
        ],
        "gate": "g1_vo_pickup",
        "optional": True,
        "label_detail": "Optional gap framing (questions, summaries, prefaces)",
    },
    {
        "id": "plan_rank",
        "label": "Plan & rank",
        "description": "Coverage + narrative, ranking, nugget layups, gap recompose.",
        "stages": [
            "topic_coverage_audit",
            "narrative_arc_plan",
            "connector_fuse_pass_pre_ranking",
            "full_master_ranking",
            "nugget_corpus_mine",
            "information_package_plan",
            "nugget_layup_compose",
            "refinement_agenda",
            "gap_framing_recompose",
            "selection_framing_apply",
            "transitions",
        ],
        "gate": None,
    },
    {
        "id": "edit",
        "label": "Edit",
        "description": "Optional NLE timeline trims (Timeline tab).",
        "stages": [],
        "gate": None,
        "nle": True,
    },
    {
        "id": "sound",
        "label": "Sound",
        "description": "Sound design plan, VO finalize, SFX prompt craft.",
        "stages": ["sound_design_plan", "sound_design_vo_finalize", "sfx_prompt_craft"],
        "gate": None,
    },
    {
        "id": "build",
        "label": "Build",
        "description": "EDL, preview, listen delight, MMAudio, mix, junction QA.",
        "stages": [
            "edl_narrative_audit",
            "edl",
            "assembly_preview",
            "listen_delight_audit",
            "mmaudio_sfx",
            "mix",
            "junction_snip_qa",
        ],
        "gate": None,
    },
    {
        "id": "ship",
        "label": "Ship",
        "description": "Master finalize and optional local episode package; S3/RSS sync is separate.",
        "stages": [
            "master_finalize",
            "episode_meta_build",
            "episode_cover_prompt_craft",
            "podcast_encode_mp3",
            "episode_cover_generate",
            "podcast_publish",
        ],
        "gate": "g_publish",
    },
]


def phase_for_stage(stage_id: str) -> dict[str, Any] | None:
    for phase in PHASES:
        if stage_id in phase.get("stages") or []:
            return phase
        if phase.get("gate") == stage_id:
            return phase
    return None


def all_phase_stage_ids() -> list[str]:
    out: list[str] = []
    for phase in PHASES:
        out.extend(phase.get("stages") or [])
    return out
