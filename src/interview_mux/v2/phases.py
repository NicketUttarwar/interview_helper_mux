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
        "stages": ["audio_preclean", "ingest", "transcribe", "transcript_review_build"],
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
        "description": "Shared analysis: speakers, segments, sonic context, delivery brief.",
        "stages": [
            "source_acoustic_profile",
            "interview_spine_build",
            "speaker_roles",
            "source_topology_build",
            "content_context",
            "boundary_detection",
            "segment_classification",
            "content_brief_reanchor",
            "sonic_context_build",
            "sound_design_palettes",
            "delivery_brief_build",
            "soundscape_policy_build",
            "episode_structure_compose",
        ],
        "gate": None,
    },
    {
        "id": "fill_gaps",
        "label": "Fill gaps",
        "description": "Optional: record pickup VO or skip and continue without gap lines.",
        "stages": ["missing_framing", "optimal_questions"],
        "gate": "g1_vo_pickup",
        "optional": True,
    },
    {
        "id": "plan_rank",
        "label": "Plan & rank",
        "description": "Coverage audit, narrative plan, master ranking, transitions.",
        "stages": [
            "topic_coverage_audit",
            "narrative_arc_plan",
            "full_master_ranking",
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
        "description": "EDL, assembly preview, MMAudio SFX, mix.",
        "stages": ["edl_narrative_audit", "edl", "assembly_preview", "mmaudio_sfx", "mix"],
        "gate": None,
    },
    {
        "id": "ship",
        "label": "Ship",
        "description": "Master finalize and QC.",
        "stages": ["master_finalize"],
        "gate": None,
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
