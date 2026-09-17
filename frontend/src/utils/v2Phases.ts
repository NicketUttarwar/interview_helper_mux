/**
 * v2 twelve-phase operator journey — mirrors `interview_mux.v2.phases.PHASES`.
 *
 * This is a hand-maintained mirror, so `tests/test_v2_phases_mirror.py` parses the
 * `V2_PHASES` literal below and fails on any drift from the Python source of truth.
 * Keep the literal shape parseable: one property per line, no computed values.
 *
 * `understand` was one 23-stage phase; it is split into `understand-a/b/c`, each
 * carrying `legacyId: "understand"` so consumers keyed on the old id still resolve
 * via `phasesForId` / `phaseStageIds`.
 */

export interface V2Phase {
  id: string;
  label: string;
  description: string;
  stages: string[];
  gate?: string | null;
  optional?: boolean;
  nle?: boolean;
  /** Set on the `understand-a/b/c` split phases — the pre-split phase id. */
  legacyId?: string;
  labelDetail?: string;
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
    description: "Normalize audio, transcribe, build transcript review queue, probe source audio.",
    stages: [
      "audio_preclean",
      "ingest",
      "transcribe",
      "transcript_review_build",
      "audio_probe_build",
    ],
    gate: null,
  },
  {
    id: "fix_transcript",
    label: "Fix transcript",
    description: "Correct STT errors before analysis (mandatory).",
    stages: [],
    gate: "transcript_review",
  },
  {
    id: "understand-a",
    label: "Understand — transcript to segments",
    description: "Speakers, talking-points cuts, segment boundaries and classes.",
    legacyId: "understand",
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
    ],
    gate: null,
  },
  {
    id: "understand-b",
    label: "Understand — segment refinement",
    description: "Brief re-anchor, framing posture, resplit, vernacular and connector passes.",
    legacyId: "understand",
    stages: [
      "content_brief_reanchor",
      "framing_posture_decide",
      "boundary_topic_resplit",
      "vernacular_segment_sanitize",
      "low_conf_island_scan",
      "connector_fuse_pass",
    ],
    gate: null,
  },
  {
    id: "understand-c",
    label: "Understand — sonic and Shape plan",
    description: "Sonic context, palettes, mastering research waves and Shape plan.",
    legacyId: "understand",
    stages: [
      "sonic_context_build",
      "sound_design_palettes",
      "mastering_research_routing",
      "mastering_research_waves",
      "mastering_research_rollup",
      "mastering_shape_agenda",
      "mastering_shape_candidates",
      "mastering_plan_synthesize",
    ],
    gate: null,
  },
  {
    id: "fill_gaps",
    label: "Fill gaps",
    description: "Optional: interviewer framing VO (summaries, prefaces, questions) or skip.",
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
    labelDetail: "Optional gap framing (questions, summaries, prefaces)",
  },
  {
    id: "plan_rank",
    label: "Plan & rank",
    description: "Coverage + narrative, ranking, nugget layups, gap recompose.",
    stages: [
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
    gate: null,
  },
  {
    id: "edit",
    label: "Edit",
    description: "Optional NLE timeline trims (Timeline tab).",
    stages: [],
    gate: null,
    nle: true,
  },
  {
    id: "sound",
    label: "Sound",
    description: "Sound design plan (VO finalize measures seated WAVs after synth).",
    stages: ["sound_design_plan", "vo_line_adjudicate"],
    gate: null,
  },
  {
    id: "build",
    label: "Build",
    description: "Spoken VO synth, VO finalize, EDL, preview, listen delight, palette compose, MusicGen, mix, junction QA.",
    stages: [
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
    gate: null,
  },
  {
    id: "ship",
    label: "Ship",
    description: "Master finalize and optional local episode package; S3/RSS sync is separate.",
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

/** Phases matching `phaseId` by id, or by `legacyId` for the split `understand` phases. */
export function phasesForId(phaseId: string): V2Phase[] {
  const exact = V2_PHASES.filter((p) => p.id === phaseId);
  if (exact.length) return exact;
  return V2_PHASES.filter((p) => p.legacyId === phaseId);
}

/** Every stage of `phaseId`, in seed order — resolves pre-split ids like `understand`. */
export function phaseStageIds(phaseId: string): string[] {
  return phasesForId(phaseId).flatMap((p) => p.stages);
}

export function allowedPipelineSubTabsV2(): readonly string[] {
  return ["stage", "timeline"];
}
