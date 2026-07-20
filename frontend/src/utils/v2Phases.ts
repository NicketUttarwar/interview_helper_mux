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
    stages: ["audio_preclean", "ingest", "transcribe", "transcript_review_build"],
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
    description: "Shared analysis through delivery brief and episode structure.",
    stages: [
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
  },
  {
    id: "fill_gaps",
    label: "Fill gaps",
    description: "Optional: record pickup VO or skip and continue without gap lines.",
    stages: ["missing_framing", "optimal_questions"],
    gate: "g1_vo_pickup",
    optional: true,
  },
  {
    id: "plan_rank",
    label: "Plan & rank",
    description: "Coverage audit, narrative plan, master ranking, transitions.",
    stages: [
      "topic_coverage_audit",
      "narrative_arc_plan",
      "full_master_ranking",
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
    description: "EDL, assembly preview, MMAudio SFX, mix.",
    stages: ["edl_narrative_audit", "edl", "assembly_preview", "mmaudio_sfx", "mix"],
  },
  {
    id: "ship",
    label: "Ship",
    description: "Master finalize and QC.",
    stages: ["master_finalize"],
  },
];

export function isV2Enabled(config: { v2?: { enabled?: boolean } } | null | undefined): boolean {
  return config?.v2?.enabled !== false;
}

export function phaseForStage(stageId: string): V2Phase | undefined {
  return V2_PHASES.find(
    (p) => p.stages.includes(stageId) || p.gate === stageId,
  );
}

export function allowedPipelineSubTabsV2(): readonly string[] {
  return ["stage", "timeline"];
}
