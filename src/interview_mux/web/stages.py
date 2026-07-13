from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StageInfo:
    id: str
    title: str
    description: str
    phase: str  # analysis | delivery | gate
    artifacts: tuple[str, ...]
    editable: tuple[str, ...]
    audio_outputs: tuple[str, ...] = ()


ANALYSIS_STAGES_PRE_G0: tuple[StageInfo, ...] = (
    StageInfo(
        "audio_preclean",
        "Audio pre-clean",
        "Optional DeepFilterNet noise reduction before ingest; runs only when operator enables pre-clean.",
        "analysis",
        ("preclean/provider.json", "preclean/lineage.json"),
        ("run_meta.json",),
        ("preclean/isolated.wav",),
    ),
    StageInfo(
        "ingest",
        "Ingest",
        "Normalize your source recording to a standard WAV format and record checksums for traceability.",
        "analysis",
        ("ingest/checksums.json",),
        (),
        ("ingest/normalized.wav",),
    ),
    StageInfo(
        "transcribe",
        "Transcribe",
        "Run AWS Transcribe with speaker diarization to produce a word-level transcript.",
        "analysis",
        ("transcript/full.json", "transcript/speakers.json"),
        (),
    ),
    StageInfo(
        "transcript_review_build",
        "STT review prep",
        "Rank transcript clips by AWS confidence and pre-cut audio for human review.",
        "analysis",
        ("transcript/review_queue.json",),
        (),
    ),
)

DISFLUENCY_EXTRACT_STAGE = StageInfo(
    "disfluency_extract",
    "Disfluency extract",
    "Detect filler words in inter-word gaps (local VAD + Whisper) and export review clips.",
    "analysis",
    ("transcript/disfluencies.json",),
    (),
    ("glob:transcript/disfluency_clips/*.wav",),
)

# Back-compat alias: automated analysis stages in pipeline execution order (no gates).
ANALYSIS_STAGES: tuple[StageInfo, ...] = (
    *ANALYSIS_STAGES_PRE_G0,
    DISFLUENCY_EXTRACT_STAGE,
)

TRANSCRIPT_REVIEW_GATE = StageInfo(
    "transcript_review",
    "Transcript review",
    "Listen to ranked clips, correct speech-to-text errors, then mark review complete before analysis continues.",
    "gate",
    ("transcript/review_queue.json", "transcript/corrections.json"),
    ("transcript/corrections.json",),
)

DISFLUENCY_REVIEW_GATE = StageInfo(
    "disfluency_review",
    "Disfluency review",
    "Listen to detected filler clips, confirm or reject each event, then complete review before analysis continues.",
    "gate",
    ("transcript/disfluencies.json", "transcript/disfluency_review.json"),
    ("transcript/disfluencies.json",),
    ("glob:transcript/disfluency_clips/*.wav",),
)

ANALYSIS_PROFILE_STAGE = StageInfo(
    "analysis_profile",
    "Review AI story profile",
    "After understanding analysis, review AI-generated themes, major questions, tone, and pacing. Verify when ready — feeds ranking, narrative QC, and sound design.",
    "gate",
    (
        "understanding/analysis_state.json",
        "understanding/investigation_queue.json",
        "understanding/content_brief.json",
        "understanding/sound_design_plan.json",
    ),
    (
        "understanding/analysis_state.json",
        "understanding/investigation_queue.json",
        "understanding/content_brief.json",
        "understanding/sound_design_plan.json",
        "understanding/speakers.json",
        "segments/manifest.json",
    ),
)

ANALYSIS_STAGES_CONTINUED: tuple[StageInfo, ...] = (
    StageInfo(
        "source_acoustic_profile",
        "Source acoustic profile",
        "Derive per-interview pacing/energy profile and mix contract from transcript timing plus source audio.",
        "analysis",
        ("understanding/source_acoustic_profile.json",),
        ("understanding/source_acoustic_profile.json",),
    ),
    StageInfo(
        "interview_spine_build",
        "Interview comprehension spine",
        "Build time-aligned local analysis index (windows, boundary events, optional CLAP retrieval) from corrected transcript and source audio.",
        "analysis",
        ("understanding/interview_spine.json",),
        (),
    ),
    StageInfo(
        "speaker_roles",
        "Speaker roles",
        "AI identifies who is the interviewer vs interviewee and maps speaker labels to roles.",
        "analysis",
        ("understanding/speakers.json",),
        ("understanding/speakers.json",),
    ),
    StageInfo(
        "source_topology_build",
        "Source topology",
        "Classify interview shape (guest count, talk-time, frame ratio) and lock pickup voice to least-spoken speaker.",
        "analysis",
        ("understanding/source_topology.json", "understanding/flow_adaptation.json"),
        ("understanding/flow_adaptation.json",),
    ),
    StageInfo(
        "content_context",
        "Content understanding",
        "Extract themes, narrative arc, and key claims from the full transcript.",
        "analysis",
        ("understanding/content_brief.json",),
        ("understanding/content_brief.json",),
    ),
    StageInfo(
        "boundary_detection",
        "Segment boundaries",
        "Detect natural segment boundaries for editing and selection.",
        "analysis",
        ("segments/boundaries.json",),
        ("segments/boundaries.json",),
    ),
    StageInfo(
        "segment_classification",
        "Segment classification",
        "Label each segment (question, answer, aside, etc.) and build the segment manifest.",
        "analysis",
        ("segments/manifest.json",),
        ("segments/manifest.json",),
    ),
    StageInfo(
        "content_brief_reanchor",
        "Content brief re-anchor",
        "Ground topics, claims, and relationships to segment IDs after classification.",
        "analysis",
        ("understanding/content_brief.json",),
        ("understanding/content_brief.json",),
    ),
    StageInfo(
        "sonic_context_build",
        "Sonic context",
        "Consolidate scenario policy, tag registry, and cue opportunities from analysis artifacts.",
        "analysis",
        ("understanding/sonic_context.json",),
        ("understanding/sonic_context.json",),
    ),
    StageInfo(
        "sound_design_palettes",
        "Sound design palettes",
        "Create transcript-grounded sound design coherence plus reusable theme palettes.",
        "analysis",
        ("understanding/sound_design_plan.json",),
        ("understanding/sound_design_plan.json",),
    ),
    StageInfo(
        "missing_framing",
        "Gap evaluation",
        "Find missing interviewer framing and context gaps in the recording.",
        "analysis",
        ("understanding/gap_evaluations.json",),
        ("understanding/gap_evaluations.json",),
    ),
    StageInfo(
        "optimal_questions",
        "Interviewer script",
        "Generate optimal pickup lines and a human-readable VO script for any gaps.",
        "analysis",
        ("understanding/gap_report.json", "understanding/interviewer_script.txt"),
        ("understanding/gap_report.json",),
    ),
    StageInfo(
        "delivery_brief_build",
        "Delivery brief",
        "Derive adaptive soft targets (duration, question budget, chapters, SFX density) from analysis.",
        "analysis",
        ("understanding/delivery_brief.json",),
        ("understanding/delivery_brief.json",),
    ),
    StageInfo(
        "soundscape_policy_build",
        "Soundscape policy",
        "Unify acoustic, sonic, and delivery density into per-run soundscape standards and cue slots.",
        "analysis",
        ("understanding/soundscape_policy.json",),
        ("understanding/soundscape_policy.json",),
    ),
)

ANALYSIS_STAGES = ANALYSIS_STAGES + ANALYSIS_STAGES_CONTINUED

G1_STAGE = StageInfo(
    "g1_vo_pickup",
    "VO pickup (G1)",
    "Record or upload voice-over lines for gaps marked delivery: record. Each line maps to a segment on the timeline.",
    "gate",
    ("understanding/gap_report.json", "understanding/interviewer_script.txt"),
    ("understanding/gap_report.json",),
)

VO_INGEST_STAGE = StageInfo(
    "vo_ingest",
    "Merge VO pickup",
    "On-demand after G1: normalize pickup WAVs under vo_pickup/ (CLI or API single-stage run; not in default pipeline order).",
    "gate",
    ("vo_pickup/", "understanding/gap_report.json"),
    ("vo_pickup/normalized/",),
)

DELIVERY_STAGES: tuple[StageInfo, ...] = (
    StageInfo(
        "topic_coverage_audit",
        "Topic coverage",
        "Audit that every theme from the content brief is covered by selected segments.",
        "delivery",
        ("master/coverage_audit.json",),
        ("master/coverage_audit.json",),
    ),
    StageInfo(
        "narrative_arc_plan",
        "Narrative arc",
        "Plan chapters, setup → payoff structure, and ordering constraints for the full podcast.",
        "delivery",
        ("master/narrative_plan.json",),
        ("master/narrative_plan.json",),
    ),
    StageInfo(
        "full_master_ranking",
        "Segment ordering",
        "Ranked optimal segment order for the full master podcast (not chronological default).",
        "delivery",
        ("master/selection.json",),
        ("master/selection.json",),
    ),
    StageInfo(
        "transitions",
        "Transitions",
        "Generate interviewer bridge lines between segments.",
        "delivery",
        ("master/transitions.json",),
        ("master/transitions.json",),
    ),
    StageInfo(
        "sound_design_plan",
        "Sound design plan",
        "Build Flow 1 reusable sound design assets and cues in the shared sound design plan.",
        "delivery",
        ("understanding/sound_design_plan.json",),
        ("understanding/sound_design_plan.json",),
    ),
    StageInfo(
        "sound_design_vo_finalize",
        "VO bridge finalize",
        "Measure vo_pickup WAV durations and adjust VO bridge cues in the sound design plan.",
        "delivery",
        ("understanding/sound_design_plan.json", "vo_pickup/"),
        ("understanding/sound_design_plan.json",),
    ),
    StageInfo(
        "edl_narrative_audit",
        "EDL narrative audit",
        "Flagship review of final Flow 1 narrative readiness before EDL construction.",
        "delivery",
        (
            "master/edl_narrative_audit.json",
            "master/selection.json",
            "master/narrative_plan.json",
            "master/transitions.json",
        ),
        ("master/edl_narrative_audit.json",),
    ),
    StageInfo(
        "edl",
        "Edit decision list",
        "Build the EDL combining speech order, VO pickup placements, and transition anchors.",
        "delivery",
        ("master/edl.json",),
        ("master/edl.json",),
    ),
    StageInfo(
        "assembly_preview",
        "Assembly preview",
        "Render speech + recorded VO only (no MMAudio SFX) so you can listen before generation.",
        "delivery",
        ("master/edl.json",),
        (),
        ("master/assembly_preview.wav",),
    ),
    StageInfo(
        "g1_5_preview_pickup",
        "Post-preview pickup (G1.5)",
        "TBIY only: after listening to assembly preview, re-record reaction lines with preview context.",
        "gate",
        ("understanding/gap_report.json", "vo_pickup/"),
        ("understanding/gap_report.json", "vo_pickup/"),
    ),
    StageInfo(
        "sfx_prompt_craft",
        "Craft MMAudio prompts",
        "Build one MMAudio text-to-audio prompt per planned asset_id (positive + negative). "
        "When G1.5 is enabled (g1_5_require_prompt_approval), review and approve prompts here before SFX generation.",
        "delivery",
        ("sound_design/sfx_prompts.json",),
        ("sound_design/sfx_prompts.json",),
    ),
    StageInfo(
        "mmaudio_sfx",
        "Generate SFX",
        "Local MMAudio text-to-audio per unique asset_id; writes sound_design/assets/{asset_id}.wav.",
        "delivery",
        ("understanding/sound_design_plan.json", "sound_design/sfx_prompts.json"),
        (),
        ("sound_design/assets/", "master/sfx/"),
    ),
    StageInfo(
        "mix",
        "Mix assembly",
        "Mix speech, VO, beds, and stingers into a pre-master assembly WAV.",
        "delivery",
        ("master/assembly.wav",),
        (),
        ("master/assembly.wav",),
    ),
    StageInfo(
        "master_finalize",
        "Master export",
        "Apply loudness mastering (−16 LUFS) and export the final podcast.",
        "delivery",
        (),
        (),
        ("master/master.wav",),
    ),
)


_LEGACY_STAGE_ALIASES: tuple[StageInfo, ...] = (
    StageInfo(
        "mux_flow1",
        "Assembly (legacy)",
        "Backward-compatible id for mix.",
        "delivery",
        ("master/assembly.wav",),
        (),
        ("master/assembly.wav",),
    ),
    StageInfo(
        "podcast_sfx_brief",
        "SFX brief (v1 legacy)",
        "v1 one-shot brief — not on the default delivery path. Use sound_design_plan instead.",
        "delivery",
        ("master/podcast_sfx_brief.json",),
        ("master/podcast_sfx_brief.json",),
    ),
)

STAGE_BY_ID: dict[str, StageInfo] = {
    s.id: s
    for s in (
        *ANALYSIS_STAGES,
        TRANSCRIPT_REVIEW_GATE,
        DISFLUENCY_REVIEW_GATE,
        ANALYSIS_PROFILE_STAGE,
        G1_STAGE,
        VO_INGEST_STAGE,
        *DELIVERY_STAGES,
        *_LEGACY_STAGE_ALIASES,
    )
}

# External API providers required before execute (GUI session consent).
STAGE_API_PROVIDERS: dict[str, tuple[str, ...]] = {
    "transcribe": ("aws",),
    "speaker_roles": ("openai",),
    "content_context": ("openai",),
    "boundary_detection": ("openai",),
    "segment_classification": ("openai",),
    "content_brief_reanchor": ("openai",),
    "sound_design_palettes": ("openai",),
    "missing_framing": ("openai",),
    "optimal_questions": ("openai",),
    "topic_coverage_audit": ("openai",),
    "narrative_arc_plan": ("openai",),
    "full_master_ranking": ("openai",),
    "transitions": ("openai",),
    "sound_design_plan": ("openai",),
    "sfx_prompt_craft": ("openai",),
    "mmaudio_sfx": (),
    "podcast_sfx_brief": ("openai",),
}

EXECUTABLE_ORDER: dict[str, list[str]] = {
    "analysis": [s.id for s in ANALYSIS_STAGES],
    "delivery": [s.id for s in DELIVERY_STAGES if s.phase != "gate"],
}

# Stages that may surface LLM routing attempts in the GUI (OpenAI-backed or analysis loop).
LLM_ROUTING_STAGE_IDS: frozenset[str] = frozenset(
    {
        *STAGE_API_PROVIDERS.keys(),
        "sound_design_vo_finalize",
    }
)


def stage_status(ctx_done: Any, stage_id: str) -> str:
    if stage_id == "g1_vo_pickup":
        return "pending"  # resolved by caller
    if stage_id == "g1_5_preview_pickup":
        return "pending"  # resolved by caller
    if ctx_done(stage_id):
        return "done"
    return "pending"


def operator_stages_for_run(selected_flow: str | None = None) -> tuple[StageInfo, ...]:
    """Operator sidebar / GUI order: gates interleaved where they block downstream work."""
    _ = selected_flow
    return (
        *ANALYSIS_STAGES_PRE_G0,
        TRANSCRIPT_REVIEW_GATE,
        DISFLUENCY_EXTRACT_STAGE,
        DISFLUENCY_REVIEW_GATE,
        *ANALYSIS_STAGES_CONTINUED,
        ANALYSIS_PROFILE_STAGE,
        G1_STAGE,
        *DELIVERY_STAGES,
    )


def operator_linear_stage_ids(selected_flow: str | None = None) -> list[str]:
    return [s.id for s in operator_stages_for_run(selected_flow)]


def all_stages_for_run(selected_flow: str | None) -> list[dict[str, Any]]:
    return [_stage_dict(s) for s in operator_stages_for_run(selected_flow)]


def _stage_dict(s: StageInfo) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "description": s.description,
        "phase": s.phase,
        "artifacts": list(s.artifacts),
        "editable": list(s.editable),
        "audio_outputs": list(s.audio_outputs),
        "api_providers": list(STAGE_API_PROVIDERS.get(s.id, ())),
        "reuse_policy": reuse_policy_for(s.id),
    }


# Reuse eligibility vs immediate-previous execution (hash-gated copy).
_STAGE_REUSE_POLICY: dict[str, str] = {
    sid: "eligible"
    for sid in (
        "audio_preclean",
        "ingest",
        "transcribe",
        "transcript_review_build",
        "disfluency_extract",
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
        "missing_framing",
        "optimal_questions",
        "delivery_brief_build",
        "soundscape_policy_build",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "transitions",
        "sound_design_plan",
        "sound_design_vo_finalize",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "mix",
        "master_finalize",
        "transcript_review",
        "analysis_profile",
        "g1_vo_pickup",
        "g1_5_preview_pickup",
        "mux_flow1",
    )
}
_STAGE_REUSE_POLICY.update(
    {
        "vo_ingest": "on_demand",
        "disfluency_review": "gate",
        "transcript_review": "gate",
        "analysis_profile": "gate",
        "g1_vo_pickup": "gate",
        "g1_5_preview_pickup": "gate",
    }
)


def reuse_policy_for(stage_id: str) -> str:
    """Return reuse policy: eligible | gate | on_demand | none."""
    if stage_id in _STAGE_REUSE_POLICY:
        return _STAGE_REUSE_POLICY[stage_id]
    info = STAGE_BY_ID.get(stage_id)
    if not info:
        return "none"
    if info.phase == "gate":
        return "gate"
    return "none"
