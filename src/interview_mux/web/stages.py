from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StageInfo:
    id: str
    title: str
    description: str
    phase: str  # analysis | flow1 | flow2 | flow3 | gate
    artifacts: tuple[str, ...]
    editable: tuple[str, ...]
    audio_outputs: tuple[str, ...] = ()


ANALYSIS_STAGES: tuple[StageInfo, ...] = (
    StageInfo(
        "audio_preclean",
        "Audio pre-clean (optional)",
        "Optional ElevenLabs noise isolation before ingest; runs only when operator enables pre-clean.",
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

TRANSCRIPT_REVIEW_GATE = StageInfo(
    "transcript_review",
    "Transcript review",
    "Listen to ranked clips, correct speech-to-text errors, then mark review complete before analysis continues.",
    "gate",
    ("transcript/review_queue.json", "transcript/corrections.json"),
    ("transcript/corrections.json",),
)

ANALYSIS_PROFILE_STAGE = StageInfo(
    "analysis_profile",
    "Lock story for podcast edit",
    "Themes, major questions, tone, and pacing. Verify when ready — feeds ranking, narrative QC, and sound design.",
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
        "speaker_roles",
        "Speaker roles",
        "AI identifies who is the interviewer vs interviewee and maps speaker labels to roles.",
        "analysis",
        ("understanding/speakers.json",),
        ("understanding/speakers.json",),
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

FLOW1_STAGES: tuple[StageInfo, ...] = (
    StageInfo(
        "topic_coverage_audit",
        "Topic coverage",
        "Audit that every theme from the content brief is covered by selected segments.",
        "flow1",
        ("flow_1_master/coverage_audit.json",),
        ("flow_1_master/coverage_audit.json",),
    ),
    StageInfo(
        "narrative_arc_plan",
        "Narrative arc",
        "Plan chapters, setup → payoff structure, and ordering constraints for the full podcast.",
        "flow1",
        ("flow_1_master/narrative_plan.json",),
        ("flow_1_master/narrative_plan.json",),
    ),
    StageInfo(
        "full_master_ranking",
        "Segment ordering",
        "Ranked optimal segment order for the full master podcast (not chronological default).",
        "flow1",
        ("flow_1_master/selection.json",),
        ("flow_1_master/selection.json",),
    ),
    StageInfo(
        "transitions",
        "Transitions",
        "Generate interviewer bridge lines between segments.",
        "flow1",
        ("flow_1_master/transitions.json",),
        ("flow_1_master/transitions.json",),
    ),
    StageInfo(
        "sound_design_plan_flow1",
        "Sound design plan",
        "Build Flow 1 reusable sound design assets and cues in the shared sound design plan.",
        "flow1",
        ("understanding/sound_design_plan.json",),
        ("understanding/sound_design_plan.json",),
    ),
    StageInfo(
        "sound_design_vo_finalize",
        "VO bridge finalize",
        "Measure vo_pickup WAV durations and adjust VO bridge cues in the sound design plan.",
        "flow1",
        ("understanding/sound_design_plan.json", "vo_pickup/"),
        ("understanding/sound_design_plan.json",),
    ),
    StageInfo(
        "edl_flow1",
        "Edit decision list",
        "Build the EDL combining speech order, VO pickup placements, and transition anchors.",
        "flow1",
        ("flow_1_master/edl.json",),
        ("flow_1_master/edl.json",),
    ),
    StageInfo(
        "assembly_preview",
        "Assembly preview",
        "Render speech + recorded VO only (no ElevenLabs SFX) so you can listen before spend.",
        "flow1",
        ("flow_1_master/edl.json",),
        (),
        ("flow_1_master/assembly_preview.wav",),
    ),
    StageInfo(
        "elevenlabs_prompt_craft",
        "Craft ElevenLabs prompts",
        "Build one crafted prompt per planned asset_id. When G1.5 is enabled "
        "(g1_5_require_prompt_approval), review and approve prompts here before SFX generation.",
        "flow1",
        ("sound_design/elevenlabs_prompts.json",),
        ("sound_design/elevenlabs_prompts.json",),
    ),
    StageInfo(
        "elevenlabs_sfx_flow1",
        "Generate SFX",
        "One ElevenLabs REST call per unique asset_id; writes sound_design/assets/{asset_id}.wav.",
        "flow1",
        ("understanding/sound_design_plan.json", "sound_design/elevenlabs_prompts.json"),
        (),
        ("sound_design/assets/", "flow_1_master/sfx/"),
    ),
    StageInfo(
        "mix_flow1",
        "Mix assembly",
        "Mix speech, VO, beds, and stingers into a pre-master assembly WAV.",
        "flow1",
        ("flow_1_master/assembly.wav",),
        (),
        ("flow_1_master/assembly.wav",),
    ),
    StageInfo(
        "master_flow1",
        "Master export",
        "Apply loudness mastering (−16 LUFS) and export the final podcast.",
        "flow1",
        (),
        (),
        ("flow_1_master/master.wav",),
    ),
)

FLOW2_STAGES: tuple[StageInfo, ...] = (
    StageInfo(
        "highlight_selection",
        "Highlight selection",
        "Pick up to five punchy clips for the highlight reel.",
        "flow2",
        ("flow_2_highlights/selection.json",),
        ("flow_2_highlights/selection.json",),
    ),
    StageInfo(
        "sound_design_plan_flow2",
        "Sound design plan",
        "Build Flow 2 reusable sound design assets and cue plan in the shared sound design plan.",
        "flow2",
        ("understanding/sound_design_plan.json",),
        ("understanding/sound_design_plan.json",),
    ),
    StageInfo(
        "elevenlabs_prompt_craft",
        "Craft ElevenLabs prompts",
        "Build one crafted prompt per planned asset_id. When G1.5 is enabled "
        "(g1_5_require_prompt_approval), review and approve prompts here before SFX generation.",
        "flow2",
        ("sound_design/elevenlabs_prompts.json",),
        ("sound_design/elevenlabs_prompts.json",),
    ),
    StageInfo(
        "elevenlabs_sfx_flow2",
        "Generate SFX",
        "One ElevenLabs REST call per unique asset_id; writes sound_design/assets/{asset_id}.wav.",
        "flow2",
        ("understanding/sound_design_plan.json", "sound_design/elevenlabs_prompts.json"),
        (),
        ("sound_design/assets/", "flow_2_highlights/sfx/"),
    ),
    StageInfo(
        "mix_flow2",
        "Mix assembly",
        "Assemble highlight clips with cold open, transitions, and SFX into a pre-master WAV.",
        "flow2",
        ("flow_2_highlights/assembly.wav",),
        (),
        ("flow_2_highlights/assembly.wav",),
    ),
    StageInfo(
        "master_flow2",
        "Master export",
        "Apply loudness mastering (−14 LUFS) and export the highlight reel.",
        "flow2",
        (),
        (),
        ("flow_2_highlights/master.wav",),
    ),
)

FLOW3_STAGES: tuple[StageInfo, ...] = (
    StageInfo(
        "podcast_show_description",
        "Show description",
        "Generate a ~200-word third-person podcast blurb from shared analysis (flagship LLM).",
        "flow3",
        ("flow_3_description/show_description.json",),
        ("flow_3_description/show_description.json",),
    ),
    StageInfo(
        "export_show_description",
        "Export blurb",
        "Export plain-text show description for podcast directories (no LLM).",
        "flow3",
        ("flow_3_description/show_description.md",),
        (),
    ),
)

G2_STAGE = StageInfo(
    "g2_flow_select",
    "Confirm output (G2)",
    "Confirm full master podcast, highlight reel, or show description. Matches your intent from the start screen.",
    "gate",
    ("run_meta.json",),
    ("run_meta.json",),
)

_LEGACY_STAGE_ALIASES: tuple[StageInfo, ...] = (
    StageInfo(
        "mux_flow1",
        "Assembly (legacy)",
        "Backward-compatible id for mix_flow1.",
        "flow1",
        ("flow_1_master/assembly.wav",),
        (),
        ("flow_1_master/assembly.wav",),
    ),
    StageInfo(
        "mux_flow2",
        "Micro-assembly (legacy)",
        "Backward-compatible id for mix_flow2.",
        "flow2",
        ("flow_2_highlights/assembly.wav",),
        (),
        ("flow_2_highlights/assembly.wav",),
    ),
    StageInfo(
        "podcast_sfx_brief",
        "SFX brief (v1 legacy)",
        "v1 one-shot brief — not on the default Flow 1 path. Use sound_design_plan_flow1 instead.",
        "flow1",
        ("flow_1_master/podcast_sfx_brief.json",),
        ("flow_1_master/podcast_sfx_brief.json",),
    ),
    StageInfo(
        "sfx_brief",
        "SFX brief (v1 legacy)",
        "v1 montage brief — not on the default Flow 2 path. Use sound_design_plan_flow2 instead.",
        "flow2",
        ("flow_2_highlights/sfx_brief.json",),
        ("flow_2_highlights/sfx_brief.json",),
    ),
)

STAGE_BY_ID: dict[str, StageInfo] = {
    s.id: s
    for s in (
        *ANALYSIS_STAGES,
        TRANSCRIPT_REVIEW_GATE,
        ANALYSIS_PROFILE_STAGE,
        G1_STAGE,
        G2_STAGE,
        *FLOW1_STAGES,
        *FLOW2_STAGES,
        *FLOW3_STAGES,
        *_LEGACY_STAGE_ALIASES,
    )
}

# External API providers required before execute (GUI session consent).
STAGE_API_PROVIDERS: dict[str, tuple[str, ...]] = {
    "audio_preclean": ("elevenlabs",),
    "transcribe": ("aws",),
    "speaker_roles": ("openai",),
    "content_context": ("openai",),
    "boundary_detection": ("openai",),
    "segment_classification": ("openai",),
    "sound_design_palettes": ("openai",),
    "missing_framing": ("openai",),
    "optimal_questions": ("openai",),
    "topic_coverage_audit": ("openai",),
    "narrative_arc_plan": ("openai",),
    "full_master_ranking": ("openai",),
    "transitions": ("openai",),
    "sound_design_plan_flow1": ("openai",),
    "sound_design_plan_flow2": ("openai",),
    "elevenlabs_prompt_craft": ("openai",),
    "elevenlabs_sfx_flow1": ("elevenlabs",),
    "elevenlabs_sfx_flow2": ("elevenlabs",),
    "highlight_selection": ("openai",),
    "podcast_show_description": ("openai",),
    "podcast_sfx_brief": ("openai",),
    "sfx_brief": ("openai",),
}

EXECUTABLE_ORDER: dict[str, list[str]] = {
    "analysis": [s.id for s in ANALYSIS_STAGES],
    "flow1": [s.id for s in FLOW1_STAGES],
    "flow2": [s.id for s in FLOW2_STAGES],
    "flow3": [s.id for s in FLOW3_STAGES],
}


def stage_status(ctx_done: Any, stage_id: str) -> str:
    if stage_id == "g1_vo_pickup":
        return "pending"  # resolved by caller
    if stage_id == "g2_flow_select":
        return "pending"  # resolved by caller
    if ctx_done(stage_id):
        return "done"
    return "pending"


def all_stages_for_run(selected_flow: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in ANALYSIS_STAGES:
        out.append(_stage_dict(s))
    out.append(_stage_dict(TRANSCRIPT_REVIEW_GATE))
    out.append(_stage_dict(ANALYSIS_PROFILE_STAGE))
    out.append(_stage_dict(G1_STAGE))
    out.append(_stage_dict(G2_STAGE))
    if selected_flow == "flow1":
        for s in FLOW1_STAGES:
            out.append(_stage_dict(s))
    elif selected_flow == "flow2":
        for s in FLOW2_STAGES:
            out.append(_stage_dict(s))
    elif selected_flow == "flow3":
        for s in FLOW3_STAGES:
            out.append(_stage_dict(s))
    return out


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
    }
