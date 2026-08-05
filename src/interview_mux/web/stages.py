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
    # Refinement Pass (see docs/cross-cutting/refinement-passes.md): True for L0 agenda,
    # gap recompose/apply, and *_refine stages so the GUI can badge them "Pass 2".
    refinement_pass: bool = False
    # For refine/recompose stages: the stage_id this pass revisits (from refinement_catalog).
    pass_of: str | None = None


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
        "Run local MLX speech-to-text with diarization to produce a word-level transcript.",
        "analysis",
        ("transcript/full.json", "transcript/speakers.json"),
        (),
    ),
    StageInfo(
        "audio_probe_build",
        "Audio probes",
        "Local audio probe platform: vernacular and pack golden facts from speaker flows.",
        "analysis",
        (
            "analysis/run_golden_facts.json",
            "transcript/protected_zones.json",
            "transcript/speaker_flows.json",
            "vernacular/probe_report.json",
            "vernacular/audio_tags_by_flow.json",
        ),
        (),
    ),
    StageInfo(
        "transcript_review_build",
        "STT review prep",
        "Rank transcript clips by local STT confidence and pre-cut audio for human review.",
        "analysis",
        ("transcript/review_queue.json", "transcript/corrections.json"),
        (),
        ("glob:transcript/review_clips/*.wav",),
    ),
)

# Back-compat alias: automated analysis stages in pipeline execution order (no gates).
ANALYSIS_STAGES: tuple[StageInfo, ...] = ANALYSIS_STAGES_PRE_G0

TRANSCRIPT_REVIEW_GATE = StageInfo(
    "transcript_review",
    "Transcript review",
    "Listen to ranked clips, correct speech-to-text errors, then mark review complete before analysis continues.",
    "gate",
    (
        "transcript/review_queue.json",
        "transcript/corrections.json",
        "transcript/full.json",
        "operator/transcript_corrected.json",
        "operator/transcript_corrected.txt",
        "operator/transcript_corrections.json",
    ),
    ("transcript/corrections.json", "transcript/full.json"),
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
        ("glob:understanding/speaker_samples/*.wav",),
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
        "boundary_topic_resplit",
        "Topic boundary resplit",
        "Split overloaded segments using reanchored topics and fine-grain policy.",
        "analysis",
        ("segments/boundaries.json",),
        ("segments/boundaries.json",),
    ),
    StageInfo(
        "vernacular_segment_sanitize",
        "Vernacular sanitize",
        "N-way split of segments that contain protected vernacular spans; refresh must_keep ids.",
        "analysis",
        (
            "segments/manifest.json",
            "vernacular/resplit_report.json",
            "analysis/vernacular_must_keep.json",
        ),
        (),
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
        "gap_framing_compose",
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
    StageInfo(
        "episode_structure_compose",
        "Episode structure",
        "Deterministic sparse slot plan + segment order (optional phases; no forced payoff/outro).",
        "analysis",
        ("understanding/episode_structure.json",),
        ("understanding/episode_structure.json",),
    ),
    StageInfo(
        "mastering_research_routing",
        "Mastering research routing",
        "Route research waves for the Shape Engine.",
        "analysis",
        ("mastering/research/routing.json",),
        (),
    ),
    StageInfo(
        "mastering_research_waves",
        "Mastering research waves",
        "Run mastering research wave packets.",
        "analysis",
        ("mastering/research/waves.json",),
        (),
    ),
    StageInfo(
        "mastering_research_rollup",
        "Mastering research rollup",
        "Roll up research fields for construction.",
        "analysis",
        ("mastering/research/rollup.json",),
        (),
    ),
    StageInfo(
        "mastering_shape_agenda",
        "Mastering shape agenda",
        "L0 agenda for Shape Engine candidates.",
        "analysis",
        ("mastering/shape/agenda.json",),
        (),
    ),
    StageInfo(
        "mastering_shape_candidates",
        "Mastering shape candidates",
        "Mint Shape Engine candidates.",
        "analysis",
        ("mastering/shape/candidates.json",),
        (),
    ),
    StageInfo(
        "mastering_plan_synthesize",
        "Mastering plan synthesize",
        "Synthesize mastering plan from candidates.",
        "analysis",
        ("mastering/mastering_plan.json",),
        (),
    ),
    StageInfo(
        "mastering_plan_confirm",
        "Mastering plan confirm",
        "Confirm mastering plan before gaps/delivery.",
        "analysis",
        ("mastering/mastering_plan.json",),
        (),
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

VO_SYNTHESIZE_STAGE = StageInfo(
    "vo_synthesize",
    "Synthesize gap VO",
    "On-demand at G1: local mlx-audio S2S for delivery:synthesize lines (fail-open).",
    "gate",
    ("vo_pickup/synthesized/", "understanding/gap_report.json"),
    ("vo_pickup/synthesized/",),
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
        "refinement_agenda",
        "Refinement agenda (L0)",
        "Confirm which Pass 2 classes are eligible for this tape after ranking.",
        "delivery",
        ("understanding/refinement_agenda.json",),
        ("understanding/refinement_agenda.json",),
        refinement_pass=True,
    ),
    StageInfo(
        "gap_framing_recompose",
        "Gap framing recompose (Pass 2)",
        "Rewrite host VO against kept segment order — or skip-copy draft for flow integrity.",
        "delivery",
        ("understanding/gap_report.json", "understanding/gap_framing_recompose.json"),
        ("understanding/gap_report.json",),
        refinement_pass=True,
        pass_of="gap_framing_compose",
    ),
    StageInfo(
        "selection_framing_apply",
        "Apply framing excludes",
        "Apply covered_by_framing_vo excludes after recompose with coverage guards.",
        "delivery",
        ("master/selection.json",),
        ("master/selection.json",),
        refinement_pass=True,
    ),
    StageInfo(
        "ranking_refine",
        "Ranking refine (Pass 2)",
        "Optional ranking refinement when topic holes remain.",
        "delivery",
        ("master/selection.json",),
        ("master/selection.json",),
        refinement_pass=True,
        pass_of="full_master_ranking",
    ),
    StageInfo(
        "narrative_arc_refine",
        "Narrative refine (Pass 2)",
        "Optional narrative arc refinement after gap commit.",
        "delivery",
        ("master/narrative_plan.json",),
        ("master/narrative_plan.json",),
        refinement_pass=True,
        pass_of="narrative_arc_plan",
    ),
    StageInfo(
        "transitions",
        "Transitions",
        "Generate interviewer bridge lines between segments.",
        "delivery",
        (
            "master/transitions.json",
            "understanding/synthetic_framing_plan.json",
            "understanding/synthetic_context_packet.json",
        ),
        ("master/transitions.json",),
    ),
    StageInfo(
        "transitions_refine",
        "Transitions refine (Pass 2)",
        "Optional bridge dedupe/refine against final gap VO.",
        "delivery",
        ("master/transitions.json",),
        ("master/transitions.json",),
        refinement_pass=True,
        pass_of="transitions",
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
        "sdp_intent_refine",
        "SDP intent refine (Pass 2)",
        "Optional SFX-restraint refinement of the sound design plan for the final timeline.",
        "delivery",
        ("understanding/sound_design_plan.json",),
        ("understanding/sound_design_plan.json",),
        refinement_pass=True,
        pass_of="sound_design_plan",
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
        "edl_narrative_refine",
        "EDL narrative refine (Pass 2)",
        "Optional last editorial sanity refinement before EDL construction.",
        "delivery",
        ("master/edl_narrative_audit.json",),
        ("master/edl_narrative_audit.json",),
        refinement_pass=True,
        pass_of="edl_narrative_audit",
    ),
    StageInfo(
        "edl",
        "Edit decision list",
        "Build the EDL combining speech order, VO pickup placements, and transition anchors.",
        "delivery",
        ("master/edl.json", "master/transitions/"),
        ("master/edl.json",),
        ("master/transitions/",),
    ),
    StageInfo(
        "assembly_preview",
        "Assembly preview",
        "Render speech + recorded VO only (no MMAudio SFX) so you can listen before generation.",
        "delivery",
        (),
        (),
        ("master/assembly_preview.wav",),
    ),
    StageInfo(
        "listen_delight_audit",
        "Listen delight audit",
        "Score assembly listen delight before SFX generation.",
        "delivery",
        ("master/listen_delight_audit.json",),
        (),
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
        "junction_snip_qa",
        "Junction snip QA",
        "Deterministic start/end snip QA on every junction, then one feel audit; remaster when repairs apply.",
        "delivery",
        # Reports + commitment artifacts.  EDL/assembly remasters are side effects
        # flushed by write staging (not listed here so clear_from(mix) does not
        # archive the upstream EDL ownership).
        (
            "master/junction_snip_qa.json",
            "master/junction_feel_audit.json",
            "master/seam_autopsy.json",
            "master/render_ledger.json",
            "master/failure_review.json",
            "master/remediation_plan.json",
            "master/remediation_run_log.json",
            "sound_design/placement_adjustments.json",
        ),
        (),
    ),
    StageInfo(
        "master_finalize",
        "Master export",
        "Apply loudness mastering (−16 LUFS) and export the final podcast.",
        "delivery",
        (
            "master/post_master_quality.json",
            "master/listener_scorecard.json",
        ),
        (),
        ("master/master.wav",),
    ),
    StageInfo(
        "episode_meta_build",
        "Episode title & description",
        "LLM episode title + show notes for The War Room RSS.",
        "delivery",
        ("publish/episode_meta.json",),
        (),
    ),
    StageInfo(
        "episode_cover_prompt_craft",
        "Cover prompt",
        "Flagship craft: harvest motifs → rich gpt-image prompt (asterisks-only text, without-clauses).",
        "delivery",
        ("publish/cover_prompt.json",),
        (),
    ),
    StageInfo(
        "podcast_encode_mp3",
        "Encode MP3",
        "Encode master.wav to podcast MP3 (audio/mpeg enclosure).",
        "delivery",
        ("publish/audio.mp3", "publish/master.wav"),
        (),
        ("publish/audio.mp3",),
    ),
    StageInfo(
        "episode_cover_generate",
        "Episode cover",
        "OpenAI gpt-image ×3 + flagship vision picks most brilliant (fail-open to show art).",
        "delivery",
        ("publish/cover.jpg", "publish/cover_pick.json", "publish/cover_meta.json"),
        (),
        ("publish/cover.jpg",),
    ),
    StageInfo(
        "podcast_publish",
        "Package episode",
        "Finalize local publish/ package (meta, chapters, markers). S3 upload is a separate ASSETS sync.",
        "delivery",
        (
            "publish/package_ready.json",
            "publish/publish_result.json",
            "publish/chapters.json",
        ),
        (),
    ),
)


_LEGACY_STAGE_ALIASES: tuple[StageInfo, ...] = (
    StageInfo(
        "optimal_questions",
        "Interviewer script (legacy)",
        "Backward-compatible id for gap_framing_compose.",
        "analysis",
        ("understanding/gap_report.json", "understanding/interviewer_script.txt"),
        ("understanding/gap_report.json",),
    ),
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
        G1_STAGE,
        VO_SYNTHESIZE_STAGE,
        VO_INGEST_STAGE,
        *DELIVERY_STAGES,
        *_LEGACY_STAGE_ALIASES,
    )
}

# External API providers required before execute (GUI session consent).
STAGE_API_PROVIDERS: dict[str, tuple[str, ...]] = {
    "transcribe": ("local",),
    "speaker_roles": ("openai",),
    "content_context": ("openai",),
    "boundary_detection": ("openai",),
    "segment_classification": ("openai",),
    "content_brief_reanchor": ("openai",),
    "boundary_topic_resplit": ("openai",),
    "sound_design_palettes": ("openai",),
    "missing_framing": ("openai",),
    "gap_framing_compose": ("openai",),
    "optimal_questions": ("openai",),
    "topic_coverage_audit": ("openai",),
    "narrative_arc_plan": ("openai",),
    "full_master_ranking": ("openai",),
    "transitions": ("openai",),
    "sound_design_plan": ("openai",),
    "sfx_prompt_craft": ("openai",),
    "mmaudio_sfx": (),
    "podcast_sfx_brief": ("openai",),
    "episode_meta_build": ("openai",),
    "episode_cover_prompt_craft": ("openai",),
    "podcast_encode_mp3": (),
    "episode_cover_generate": ("openai",),
    "podcast_publish": (),
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
        *ANALYSIS_STAGES_CONTINUED,
        G1_STAGE,
        *DELIVERY_STAGES,
    )


def operator_linear_stage_ids(selected_flow: str | None = None) -> list[str]:
    return [s.id for s in operator_stages_for_run(selected_flow)]


def all_stages_for_run(selected_flow: str | None) -> list[dict[str, Any]]:
    return [_stage_dict(s) for s in operator_stages_for_run(selected_flow)]


def _stage_dict(s: StageInfo) -> dict[str, Any]:
    d: dict[str, Any] = {
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
    if s.refinement_pass:
        d["refinement_pass"] = True
    if s.pass_of:
        d["pass_of"] = s.pass_of
    return d


# Reuse eligibility vs immediate-previous execution (hash-gated copy).
_STAGE_REUSE_POLICY: dict[str, str] = {
    sid: "eligible"
    for sid in (
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
        "vernacular_segment_sanitize",
        "sonic_context_build",
        "sound_design_palettes",
        "missing_framing",
        "gap_framing_compose",
        "optimal_questions",
        "delivery_brief_build",
        "soundscape_policy_build",
        "episode_structure_compose",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "refinement_agenda",
        "gap_framing_recompose",
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
        "listen_delight_audit",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "episode_meta_build",
        "episode_cover_prompt_craft",
        "podcast_encode_mp3",
        "episode_cover_generate",
        "podcast_publish",
        "transcript_review",
        "g1_vo_pickup",
        "g1_5_preview_pickup",
        "mux_flow1",
    )
}
_STAGE_REUSE_POLICY.update(
    {
        "vo_ingest": "on_demand",
        "transcript_review": "gate",
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
