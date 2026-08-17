/** v2 ten-phase operator journey — mirrors interview_mux.v2.phases.PHASES */

export interface V2Phase {
  id: string;
  label: string;
  description: string;
  stages: string[];
  gate?: string | null;
  optional?: boolean;
  nle?: boolean;
}

export const V2_PHASES: V2Phase[] = [
  {
    id: "start",
    label: "Start",
    description: "Select interview audio; optional background-noise pre-clean offer.",
    stages: [],
    gate: null,
  },
  {
    id: "prepare",
    label: "Prepare",
    description: "Normalize audio, transcribe, build transcript review queue.",
    stages: [
      "audio_preclean",
      "ingest",
      "transcribe",
      "audio_probe_build",
      "transcript_review_build",
    ],
  },
  {
    id: "fix_transcript",
    label: "Fix transcript",
    description: "Correct STT errors before analysis (mandatory).",
    stages: [],
    gate: "transcript_review",
  },
  {
    id: "understand",
    label: "Understand",
    description: "Speakers, talking-points cuts, segments, research + Shape plan.",
    stages: [
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
      "sonic_context_build",
      "sound_design_palettes",
      "mastering_research_routing",
      "mastering_research_waves",
      "mastering_research_rollup",
      "mastering_shape_agenda",
      "mastering_shape_candidates",
      "mastering_plan_synthesize",
    ],
  },
  {
    id: "fill_gaps",
    label: "Fill gaps",
    description: "Optional: record pickup VO or skip and continue without gap lines.",
    stages: [
      "missing_framing",
      "mastering_plan_confirm",
      "gap_framing_compose",
      "delivery_brief_build",
      "soundscape_policy_build",
      "episode_structure_compose",
    ],
    gate: "g1_vo_pickup",
    optional: true,
  },
  {
    id: "plan_rank",
    label: "Plan & rank",
    description: "Coverage + narrative (deterministic when cuts bound), ranking, gap recompose.",
    stages: [
      "topic_coverage_audit",
      "narrative_arc_plan",
      "full_master_ranking",
      "refinement_agenda",
      "gap_framing_recompose",
      "selection_framing_apply",
      "transitions",
    ],
  },
  {
    id: "edit",
    label: "Edit",
    description: "Optional NLE timeline trims (Timeline tab).",
    stages: [],
    nle: true,
  },
  {
    id: "sound",
    label: "Sound",
    description: "Sound design plan, VO finalize, SFX prompt craft.",
    stages: ["sound_design_plan", "sound_design_vo_finalize", "sfx_prompt_craft"],
  },
  {
    id: "build",
    label: "Build",
    description: "EDL, preview, listen delight, MMAudio, mix, junction QA.",
    stages: [
      "edl_narrative_audit",
      "edl",
      "assembly_preview",
      "listen_delight_audit",
      "mmaudio_sfx",
      "mix",
      "junction_snip_qa",
    ],
  },
  {
    id: "ship",
    label: "Ship",
    description: "Master finalize and optional local episode package.",
    stages: [
      "master_finalize",
      "master_transcript_build",
      "episode_meta_build",
      "episode_cover_prompt_craft",
      "podcast_encode_mp3",
      "episode_cover_generate",
      "podcast_publish",
    ],
    gate: "g_publish",
  },
];

export function isV2Enabled(config: { v2?: { enabled?: boolean } } | null | undefined): boolean {
  return config?.v2?.enabled !== false;
}

/** v2 auto-commits stage outputs — write-approval pauses are disabled. */
export function v2AutoCommitArtifacts(
  config?: { v2?: { auto_commit_artifacts?: boolean } } | null,
): boolean {
  return config?.v2?.auto_commit_artifacts !== false;
}

export function phaseForStage(stageId: string): V2Phase | undefined {
  return V2_PHASES.find(
    (p) => p.stages.includes(stageId) || p.gate === stageId,
  );
}

export function allowedPipelineSubTabsV2(): readonly string[] {
  return ["stage", "timeline"];
}
