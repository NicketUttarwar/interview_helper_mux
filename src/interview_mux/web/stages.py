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
        "Normalize source to standard WAV, stabilize loudness for listening (−18 LUFS), and record checksums.",
        "analysis",
        ("ingest/checksums.json", "ingest/loudness.json"),
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
        "talking_points_compose",
        "Talking points",
        "Holistic read: decide which talking points the master must land before cutting segments.",
        "analysis",
        ("understanding/talking_points.json",),
        ("understanding/talking_points.json",),
    ),
    StageInfo(
        "ideal_cuts_propose",
        "Ideal cuts",
        "Propose the best native timed windows that prove each talking point.",
        "analysis",
        ("understanding/ideal_cuts.json",),
        ("understanding/ideal_cuts.json",),
    ),
    StageInfo(
        "ideal_cuts_materialize",
        "Materialize ideal cuts",
        "Snap cut windows to word timestamps; optionally publish boundaries and a ranking seed.",
        "analysis",
        (
            "understanding/ideal_cuts_materialized.json",
            "understanding/ideal_cuts_selection_seed.json",
            "segments/boundaries.json",
        ),
        ("understanding/ideal_cuts_materialized.json",),
    ),
    StageInfo(
        "boundary_detection",
        "Segment boundaries",
        "Detect natural segment boundaries for editing and selection (or verify ideal-cut boundaries).",
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
        "framing_posture_decide",
        "Framing posture (advisory)",
        "Homunculus 0.1.0+: LLM recommends Yes/No/sparse for G-Framing; monologue skips without LLM.",
        "analysis",
        ("understanding/framing_posture_decision.json",),
        ("understanding/framing_posture_decision.json",),
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
        "low_conf_island_scan",
        "Low-conf density must-keep",
        "Recall-first low-confidence cluster ladder; density-rank natives; hard-include top 10%.",
        "analysis",
        (
            "analysis/low_conf_islands.json",
            "analysis/low_conf_density_ranking.json",
            "analysis/low_conf_must_keep.json",
        ),
        (),
    ),
    StageInfo(
        "connector_fuse_pass",
        "Fuse mid-thought cuts",
        "Seam adjudicate — fuse mid-thought cuts (economy LLM over every adjacent pair).",
        "analysis",
        (
            "analysis/connector_seam_packets.json",
            "analysis/connector_fuse_audit.json",
            "segments/manifest.json",
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
        "Create transcript-grounded sound design coherence plus reusable theme palettes (early LLM optional).",
        "analysis",
        ("understanding/sound_design_plan.json",),
        ("understanding/sound_design_plan.json",),
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
        ("mastering/research/waves.json", "mastering/research/"),
        (),
    ),
    StageInfo(
        "mastering_research_rollup",
        "Mastering research rollup",
        "Roll up research fields for construction.",
        "analysis",
        ("mastering/research/rollup.json", "mastering/research_dossier.json"),
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
        "missing_framing",
        "Gap evaluation",
        "Find missing interviewer framing and context gaps in the recording.",
        "analysis",
        ("understanding/gap_evaluations.json",),
        ("understanding/gap_evaluations.json",),
    ),
    StageInfo(
        "mastering_plan_confirm",
        "Mastering plan confirm",
        "Confirm mastering plan before gaps/delivery.",
        "analysis",
        ("mastering/mastering_plan.json",),
        (),
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
        (
            "understanding/episode_structure.json",
            "understanding/episode_structure_compact.txt",
        ),
        ("understanding/episode_structure.json",),
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
    "Synthesize spoken VO",
    "Generate current-pair transition WAVs and remaining delivery:synthesize gap lines (fail-open). G1 API still synthesizes one line.",
    "delivery",
    ("mastering/vo_synthesize.json", "master/transitions/", "vo_pickup/synthesized/"),
    ("mastering/vo_synthesize.json",),
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
        "chapter_close_hitch",
        "Chapter-close hitch",
        "One-shot recut of native ends toward chapter/talking-point closes, remap segment ids, then continue.",
        "delivery",
        (
            "mastering/chapter_close_hitch.json",
            "mastering/chapter_close_hitch/intent_plan.json",
            "mastering/chapter_close_hitch/remap.json",
            "understanding/episode_structure_compact.txt",
            "segments/boundaries.json",
        ),
        (),
    ),
    StageInfo(
        "connector_fuse_pass_pre_ranking",
        "Pre-ranking seam fuse",
        "Second connector fuse pass before ranking so mid-thought chops do not survive into selection.",
        "delivery",
        (
            "analysis/connector_fuse_rounds.json",
            "segments/manifest.json",
        ),
        (),
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
        "selection_order_sanitize",
        "Selection order sanitize",
        "Non-amplifying cleanup of locked air order (fragment depth, spans, never-touch).",
        "delivery",
        ("master/selection.json",),
        ("master/selection.json",),
    ),
    StageInfo(
        "air_script_compose",
        "Air-script Pass A",
        "Paper-edit membership, order, cold open, omits, and story spine on mastering_plan.",
        "delivery",
        ("mastering/mastering_plan.json", "master/selection.json"),
        ("mastering/mastering_plan.json",),
    ),
    StageInfo(
        "nugget_corpus_mine",
        "Nugget corpus mine",
        "Flagship mine of grounded facts from the full transcript including excluded natives.",
        "delivery",
        ("understanding/nugget_corpus.json",),
        ("understanding/nugget_corpus.json",),
    ),
    StageInfo(
        "information_package_plan",
        "Information package plan",
        "High-bar mid-episode information packages (≤2) + ensure required episode_close music on mastering_plan.",
        "delivery",
        (
            "mastering/shape/information_package_candidates.json",
            "mastering/shape/information_packages_audit.json",
            "mastering/mastering_plan.json",
        ),
        ("mastering/mastering_plan.json",),
    ),
    StageInfo(
        "nugget_layup_compose",
        "Nugget lay-up compose",
        "Flagship per-native synthetic VO lay-ups; publishes authoritative before-VO into gap_report.",
        "delivery",
        ("understanding/nugget_layup_plan.json", "understanding/gap_report.json"),
        ("understanding/nugget_layup_plan.json", "understanding/gap_report.json"),
    ),
    StageInfo(
        "gap_report_sanitize",
        "Gap report sanitize",
        "Shape/dedupe/rebase gap_report after layups; no seat/omit authority.",
        "delivery",
        ("understanding/gap_report.json",),
        ("understanding/gap_report.json",),
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
        "Thin adapter when nugget layups own gap_report; otherwise rewrite host VO against kept order.",
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
        "air_script_seams",
        "Air-script Pass B",
        "Per-seam montage moves, VO seats, and sonic opportunity hunt on mastering_plan.",
        "delivery",
        ("mastering/mastering_plan.json",),
        ("mastering/mastering_plan.json",),
    ),
    StageInfo(
        "air_contract_sanitize",
        "Air-contract sanitize",
        "Clamp seats to rendered WAVs and sync omit flags before transitions.",
        "delivery",
        ("mastering/mastering_plan.json",),
        ("mastering/mastering_plan.json",),
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
        "sound_design_plan",
        "Sound design plan",
        "Build Flow 1 reusable sound design assets and cues in the shared sound design plan.",
        "delivery",
        (
            "understanding/sound_design_plan.json",
            "understanding/episode_structure_compact.txt",
        ),
        ("understanding/sound_design_plan.json",),
    ),
    StageInfo(
        "vo_line_adjudicate",
        "VO line adjudicate",
        "Smart second-pass LLM adjudication of body layup lines before synthesis (homunculus 0.1.0+).",
        "delivery",
        (
            "understanding/vo_line_adjudication.json",
            "understanding/gap_report.json",
        ),
        (
            "understanding/vo_line_adjudication.json",
        ),
    ),
    StageInfo(
        "vo_synthesize",
        "Synthesize spoken VO",
        "Generate current-pair transition WAVs and remaining delivery:synthesize gap lines (fail-open). G1 API still synthesizes one line.",
        "delivery",
        ("mastering/vo_synthesize.json", "master/transitions/", "vo_pickup/synthesized/"),
        ("mastering/vo_synthesize.json",),
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
        "Flagship review of final Flow 1 narrative readiness after VO synthesis (heard WAV flow).",
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
        ("mastering/listen_delight_audit.json",),
        (),
    ),
    StageInfo(
        "music_palette_compose",
        "Music palette compose",
        "Place fixed MusicGen palette assets (motif, loops, stingers, full beds) into the master cue timeline.",
        "delivery",
        ("understanding/sound_design_plan.json", "sound_design/music_palette_compose.json"),
        ("understanding/sound_design_plan.json", "sound_design/music_palette_compose.json"),
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
        "Craft MusicGen prompts",
        "Build one succinct MusicGen text-to-music prompt per palette asset_id (positive + negative). "
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
        (
            "understanding/sound_design_plan.json",
            "sound_design/sfx_prompts.json",
            "sound_design/mmaudio_qa.json",
        ),
        (),
        ("sound_design/assets/", "master/sfx/"),
    ),
    StageInfo(
        "mix",
        "Mix assembly",
        "Mix speech, VO, beds, and stingers into a pre-master assembly WAV.",
        "delivery",
        ("master/assembly.wav", "master/music_cue_coverage.json"),
        (),
        ("master/assembly.wav",),
    ),
    StageInfo(
        "junction_snip_qa",
        "Junction snip QA",
        "Deterministic start/end snip QA, batched thought-complete recuts, then one feel audit; remaster when repairs apply.",
        "delivery",
        # Reports + commitment artifacts.  EDL/assembly remasters are side effects
        # flushed by write staging (not listed here so clear_from(mix) does not
        # archive the upstream EDL ownership).
        (
            "master/junction_snip_qa.json",
            "master/junction_thought_complete.json",
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
            # The authoritative ship-time delight verdict is written here (staged);
            # undeclared staged paths are dropped at flush, so exec_11871 shipped
            # with a pre-mix advisory audit from hours earlier.
            "mastering/listen_delight_audit.json",
            "master/seam_autopsy.json",
        ),
        (),
        ("master/master.wav",),
    ),
    StageInfo(
        "master_transcript_build",
        "Master transcript",
        "Assemble the Apple-ready episode transcript from per-asset sidecars after master.wav exists.",
        "delivery",
        (
            "master/transcript.json",
            "master/transcript.vtt",
            "master/transcript.txt",
        ),
        (),
    ),
    StageInfo(
        "episode_meta_build",
        "Episode title & description",
        "LLM episode title + show notes for Zero Shot Podcast DEMO RSS.",
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
        "Finalize local publish/ package (meta, chapters, markers). S3 upload is a separate this-run sync.",
        "delivery",
        (
            # The whole local episode package — `operator_visible_staging_path`
            # filters the flush by these specs, so anything missing here is written
            # to staging and then dropped. exec_11871 shipped a package_ready.json
            # that promised episode.json / description.txt neither of which existed.
            "publish/package_ready.json",
            "publish/publish_result.json",
            "publish/chapters.json",
            "publish/transcript.vtt",
            "publish/episode.json",
            "publish/description.txt",
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
    "talking_points_compose": ("openai",),
    "ideal_cuts_propose": ("openai",),
    "boundary_detection": ("openai",),
    "segment_classification": ("openai",),
    "content_brief_reanchor": ("openai",),
    "framing_posture_decide": ("openai",),
    "boundary_topic_resplit": ("openai",),
    "sound_design_palettes": ("openai",),
    "missing_framing": ("openai",),
    "gap_framing_compose": ("openai",),
    "optimal_questions": ("openai",),
    "topic_coverage_audit": ("openai",),
    "narrative_arc_plan": ("openai",),
    "connector_fuse_pass_pre_ranking": ("openai",),
    "full_master_ranking": ("openai",),
    "air_script_compose": (),
    "connector_seam_adjudicate": ("openai",),
    "connector_fuse_pass": ("openai",),
    "low_conf_island_scan": (),
    "nugget_corpus_mine": ("openai",),
    "information_package_plan": (),
    "nugget_layup_compose": ("openai",),
    "air_script_seams": (),
    "transitions": ("openai",),
    "sound_design_plan": ("openai",),
    "music_palette_compose": ("openai",),
    "sfx_prompt_craft": ("openai",),
    "mmaudio_sfx": (),
    "podcast_sfx_brief": ("openai",),
    "master_transcript_build": (),
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
        "missing_framing",
        "gap_framing_compose",
        "optimal_questions",
        "delivery_brief_build",
        "soundscape_policy_build",
        "episode_structure_compose",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "connector_fuse_pass_pre_ranking",
        "full_master_ranking",
        "air_script_compose",
        "nugget_corpus_mine",
        "information_package_plan",
        "nugget_layup_compose",
        "refinement_agenda",
        "gap_framing_recompose",
        "selection_framing_apply",
        "air_script_seams",
        "transitions",
        "sound_design_plan",
        "vo_line_adjudicate",
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
        "master_finalize",
        "master_transcript_build",
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
        "chapter_close_hitch": "none",
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
