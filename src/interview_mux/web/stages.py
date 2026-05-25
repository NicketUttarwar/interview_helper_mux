from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StageInfo:
    id: str
    title: str
    description: str
    phase: str  # analysis | flow1 | flow2 | gate
    artifacts: tuple[str, ...]
    editable: tuple[str, ...]
    audio_outputs: tuple[str, ...] = ()


ANALYSIS_STAGES: tuple[StageInfo, ...] = (
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
    "Interview profile",
    "Per-interview themes, major questions, tone, and style. Edit and verify before or after analysis — changes feed every AI stage.",
    "gate",
    (
        "understanding/analysis_state.json",
        "understanding/investigation_queue.json",
        "understanding/content_brief.json",
    ),
    (
        "understanding/analysis_state.json",
        "understanding/investigation_queue.json",
        "understanding/content_brief.json",
        "understanding/speakers.json",
        "segments/manifest.json",
    ),
)

ANALYSIS_STAGES_CONTINUED: tuple[StageInfo, ...] = (
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
        "podcast_sfx_brief",
        "SFX brief",
        "Specify subtle podcast sound design (stingers, beds).",
        "flow1",
        ("flow_1_master/podcast_sfx_brief.json",),
        ("flow_1_master/podcast_sfx_brief.json",),
    ),
    StageInfo(
        "elevenlabs_sfx_flow1",
        "Generate SFX",
        "Generate sound effects via ElevenLabs from the SFX brief.",
        "flow1",
        ("flow_1_master/podcast_sfx_brief.json",),
        (),
    ),
    StageInfo(
        "edl_flow1",
        "Edit decision list",
        "Build the EDL combining speech, VO pickup, and SFX.",
        "flow1",
        ("flow_1_master/edl.json",),
        ("flow_1_master/edl.json",),
    ),
    StageInfo(
        "mux_flow1",
        "Assembly",
        "Mux speech, VO, and SFX into a pre-master assembly WAV.",
        "flow1",
        (),
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
        "sfx_brief",
        "Montage SFX brief",
        "Specify montage-style sound design for the highlight reel.",
        "flow2",
        ("flow_2_highlights/sfx_brief.json",),
        ("flow_2_highlights/sfx_brief.json",),
    ),
    StageInfo(
        "elevenlabs_sfx_flow2",
        "Generate SFX",
        "Generate montage sound effects via ElevenLabs.",
        "flow2",
        ("flow_2_highlights/sfx_brief.json",),
        (),
    ),
    StageInfo(
        "mux_flow2",
        "Micro-assembly",
        "Assemble highlight clips with SFX into a pre-master WAV.",
        "flow2",
        (),
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

G2_STAGE = StageInfo(
    "g2_flow_select",
    "Choose output (G2)",
    "Pick Flow 1 (full master podcast) or Flow 2 (highlight reel). This choice determines the remaining pipeline stages.",
    "gate",
    ("run_meta.json",),
    ("run_meta.json",),
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
    )
}

EXECUTABLE_ORDER: dict[str, list[str]] = {
    "analysis": [s.id for s in ANALYSIS_STAGES],
    "flow1": [s.id for s in FLOW1_STAGES],
    "flow2": [s.id for s in FLOW2_STAGES],
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
    }
