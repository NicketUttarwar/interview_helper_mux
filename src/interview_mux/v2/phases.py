"""Operator journey phases for the v2 simplified workbench.

Every stage in ``ANALYSIS_ORDER`` + ``DELIVERY_ORDER`` belongs to exactly one
phase — ``tests/test_phase_partition.py`` pins that invariant. Phase stage lists
follow seed order, so a phase boundary is always an artifact cut-point.

``understand`` was one 23-stage phase; it is split into ``understand-a/b/c`` at
artifact seams (transcript -> segments, segment refinement, sonic + Shape) per
`.cursor/plans/solver_brain_020.plan.md` §3.1. Each carries
``legacy_id: "understand"`` so consumers keyed on the old id can still resolve.
"""

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
        "description": "Normalize audio, transcribe, build transcript review queue, probe source audio.",
        "stages": [
            "audio_preclean",
            "ingest",
            "transcribe",
            "transcript_review_build",
            "audio_probe_build",
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
        "id": "understand-a",
        "label": "Understand — transcript to segments",
        "description": "Speakers, talking-points cuts, segment boundaries and classes.",
        "legacy_id": "understand",
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
        ],
        "gate": None,
    },
    {
        "id": "understand-b",
        "label": "Understand — segment refinement",
        "description": "Brief re-anchor, framing posture, resplit, vernacular and connector passes.",
        "legacy_id": "understand",
        "stages": [
            "content_brief_reanchor",
            "framing_posture_decide",
            "boundary_topic_resplit",
            "vernacular_segment_sanitize",
            "low_conf_island_scan",
            "connector_fuse_pass",
        ],
        "gate": None,
    },
    {
        "id": "understand-c",
        "label": "Understand — sonic and Shape plan",
        "description": "Sonic context, palettes, mastering research waves and Shape plan.",
        "legacy_id": "understand",
        "stages": [
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
            "chapter_close_hitch",
            "connector_fuse_pass_pre_ranking",
            "full_master_ranking",
            "selection_order_sanitize",
            "air_script_compose",
            "nugget_corpus_mine",
            "information_package_plan",
            "nugget_layup_compose",
            "gap_report_sanitize",
            "refinement_agenda",
            "gap_framing_recompose",
            "selection_framing_apply",
            "air_script_seams",
            "air_contract_sanitize",
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
        "description": "Sound design plan (VO finalize measures seated WAVs after synth).",
        "stages": ["sound_design_plan", "vo_line_adjudicate"],
        "gate": None,
    },
    {
        "id": "build",
        "label": "Build",
        "description": "Spoken VO synth, VO finalize, EDL, preview, listen delight, palette compose, MusicGen, mix, junction QA.",
        "stages": [
            "vo_synthesize",
            "sound_design_vo_finalize",
            "edl_narrative_audit",
            "edl",
            "assembly_preview",
            "listen_delight_audit",
            "music_palette_compose",
            "sfx_prompt_craft",
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
            "master_transcript_build",
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


def phases_for_id(phase_id: str) -> list[dict[str, Any]]:
    """Phases matching ``phase_id`` by id, or by ``legacy_id`` for split phases."""
    exact = [p for p in PHASES if p.get("id") == phase_id]
    if exact:
        return exact
    return [p for p in PHASES if p.get("legacy_id") == phase_id]


def phase_stage_ids(phase_id: str) -> list[str]:
    out: list[str] = []
    for phase in phases_for_id(phase_id):
        out.extend(phase.get("stages") or [])
    return out
