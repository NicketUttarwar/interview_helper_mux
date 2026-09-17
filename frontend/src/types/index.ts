export type LogLevel = "info" | "success" | "warning" | "error" | "action";

export type ToastLevel = "info" | "success" | "error" | "warning";

export interface ToastState {
  message: string;
  level: ToastLevel;
}

export interface LogEntry {
  ts: string;
  level?: LogLevel;
  message: string;
  stage?: string;
  detail?: string | Record<string, unknown> & { journey_kind?: JourneyLogKind };
}

export interface ApiProvider {
  id: string;
  label: string;
  description?: string;
  cost_hint?: string;
}

export interface AppConfig {
  assets_root: string;
  executions_root: string;
  data_root: string;
  web_port: number;
  repo_root: string;
  value_analysis_enabled?: boolean;
  disfluency_restore_enabled?: boolean;
  api_consent_persist?: boolean;
  journey_ui?: {
    enabled?: boolean;
    intent_at_start?: boolean;
    phase_sidebar?: boolean;
    story_board?: boolean;
    express_flow1?: boolean;
    journey_log_filter?: boolean;
    require_preview_listen?: boolean;
    enable_stage_reuse_offers?: boolean;
    require_write_approval_per_stage?: boolean;
    /** When true (default), auto-navigate and run automated stages after each step completes. */
    auto_advance_pipeline?: boolean;
    /** Cold-start friction collapse — see docs/workflows/first-try-reliability.md */
    first_try_mode?: boolean;
    defer_write_approval_until?: "phase_end" | "off" | "never";
    /** When true (default), defer boundary save until segment_classification unified review. */
    segmentation_unified_review?: boolean;
    preclean_auto_dismiss_when_green?: boolean;
    batch_save_phases?: string[];
  };
  /** Stage ids that may show LLM routing summary — from web/stages.py */
  llm_routing_stage_ids?: string[];
  v2?: {
    enabled?: boolean;
    auto_commit_artifacts?: boolean;
    g1_optional?: boolean;
    llm_max_attempts?: number;
  };
  v2_phases?: Array<{
    id: string;
    label: string;
    description: string;
    stages: string[];
    gate?: string | null;
    optional?: boolean;
    nle?: boolean;
  }>;
}

/**
 * Subset of {@link AppConfig} consumed by auto-advance helpers. Accepting this
 * instead of the full config lets callers pass partial configs (and tests pass
 * small literals) without widening the helpers' real dependency.
 */
export type JourneyUiConfig = Pick<AppConfig, "journey_ui">;

export interface AssetFile {
  path: string;
  name: string;
  size_bytes: number;
  modified_at?: string;
}

export interface RunSummary {
  run_id: string;
  execution_number?: number;
  input_audio_path?: string;
  source_audio_hash?: string;
  source_audio_hash_short?: string;
  updated_at?: string;
  created_at?: string;
  progress?: { done: number; total: number };
  last_log?: LogEntry;
  job_status?: string;
  last_stage?: string;
  outputs?: string[];
  operator_phase?: OperatorPhase;
  next_action?: string;
  blocking_message?: string | null;
  attention_count?: number;
  homunculus_version?: string;
  /** Pillar A ESR — prefer over sticky when progress_stale === false */
  execution_status?: ExecutionStatusSummary;
  homunculus_halt_plan?: {
    last_target?: string;
    blockers?: string[];
    attempted_heals?: string[];
    recommended_next?: string;
    pipeline_mode?: { mode?: string; decided_by?: string };
    reason?: string;
  } | null;
  podcast_id?: string;
  podcast_title?: string;
}

/** operator/execution_status.json summary folded into GUI run payloads */
export interface ExecutionStatusSummary {
  progress_stale?: boolean;
  progress_why?: string;
  current_pin?: string;
  lease?: { active?: boolean; stage?: string; reason?: string };
  sticky?: { key?: string; count?: number; halt?: boolean };
  seat_freeze?: { soft?: boolean; hard?: boolean; fingerprint?: string };
  reopen_gate?: {
    allow?: boolean;
    intent?: string;
    refuse_reason?: string;
    decision_id?: string;
  };
}

export interface HomunculusBrainInfo {
  id: string;
  label: string;
  summary: string;
  kind: "original_pipeline" | "homunculus" | string;
  prompt_tree?: string | null;
  control_plane?: "llm" | "deterministic" | string;
  is_default?: boolean;
}

export interface PodcastShowInfo {
  id: string;
  title: string;
  is_default?: boolean;
  has_artwork?: boolean;
  feed_base_url?: string;
  artwork_url?: string | null;
}

export type StageStatus =
  | "done"
  | "pending"
  | "incomplete"
  | "action_required"
  | "automation_pending"
  | "locked"
  | "awaiting_write_approval";

export type OperatorPhase =
  | "prepare"
  | "understand"
  | "complete"
  | "create"
  | "polish"
  | "ship";

export type JourneyLogKind =
  | "gate"
  | "quality"
  | "preview"
  | "sfx"
  | "qc"
  | "milestone"
  | "execute"
  | "api";

export type JourneyBlockingReason =
  | "write_approval"
  | "stage_reuse"
  | "transcript_review"
  | "g1_vo_pickup"
  | "g1_5_preview_pickup"
  | "handoff_review"
  | (string & {});

export interface JourneyBlocking {
  blocked?: boolean;
  reason?: JourneyBlockingReason | null;
  message?: string;
  stage_id?: string | null;
  reuse_candidates?: import("./index").ReuseCandidate[];
}

export interface JourneyExecuteHint {
  action?: "execute" | "checkpoint";
  mode?: string;
  label: string;
  from_stage?: string;
  until_stage?: string;
  stage_id?: string;
}

export interface JourneyState {
  phase: OperatorPhase;
  milestones: Record<string, boolean>;
  next_action: string;
  blocking: JourneyBlocking;
  delivery_readiness?: {
    ready?: boolean;
    blockers?: Array<{ layer?: string; message?: string }>;
  };
  recommended_preclean?: string | null;
  preclean_checkpoints?: string[];
  execute_hint?: JourneyExecuteHint | null;
  deliverable?: {
    kind: string;
    paths: Record<string, string>;
    qc_passed?: boolean | null;
    lufs?: number | null;
  };
  phase_progress?: Record<string, { done: number; total: number }>;
  open_investigations?: number;
  open_coherence_risks?: number;
  blocking_coherence_contradictions?: number;
  sound_labels?: string[];
  phase_guidance?: Record<string, PhaseGuidance>;
  active_substep_id?: string | null;
  active_substep_label?: string | null;
  active_operator_action?: import("./operatorAction").ServerOperatorAction;
  first_try?: {
    enabled?: boolean;
    write_approval_deferred?: boolean;
    batch_save_phases?: string[];
  };
  source_readiness?: {
    band?: string;
    score?: number;
    reasons?: string[];
    recommended?: { preclean?: boolean };
  } | null;
  pending_write_stages?: string[];
  handoff?: {
    handoff_between_stages_enabled?: boolean;
    pending_handoff_stage?: string | null;
  };
}

export type GuidanceItemStatus = "todo" | "done" | "waiting";

export interface GuidanceItem {
  id: string;
  label: string;
  status: GuidanceItemStatus;
  stage_id?: string;
  action?: string;
  kind?: string;
  substep_label?: string;
  from_stage_id?: string;
  from_stage_title?: string;
  /** upstream = prior stages; stage_health = lint/budget/cross-val blockers on this stage */
  category?: "upstream" | "stage_health" | string;
}

export interface StageGuidance {
  phase_label: string;
  prerequisites: GuidanceItem[];
  actions: GuidanceItem[];
  unlocks: string;
  steps?: StageStep[];
  artifact_checks?: Array<{
    path: string;
    label: string;
    status: GuidanceItemStatus;
  }>;
}

export type StageStepStatus = "todo" | "active" | "done" | "blocked" | "waiting" | "skipped";

export interface StageStep {
  id: string;
  number: number;
  label: string;
  instruction: string;
  review: string[];
  primary_button?: string | null;
  secondary_button?: string | null;
  kind: string;
  status: StageStepStatus;
  embed?: string | null;
  next_hint?: string | null;
  blocking_reason?: string | null;
}

export interface PhaseGuidance {
  goal: string;
  actions: GuidanceItem[];
  progress?: { done: number; total: number } | null;
}

export type StageSubstepStatus = "todo" | "done" | "waiting" | "running" | "error";

export type SubstepKind =
  | "guidance"
  | "write_approval"
  | "gate"
  | "handoff"
  | "reuse"
  | "run"
  | "checkpoint"
  | "profile"
  | "story_board"
  | "start"
  | "milestone"
  | "blocked"
  | "optional";

export interface StageSubstep {
  id: string;
  label: string;
  status: StageSubstepStatus;
  kind: SubstepKind;
  stageId: string;
  source: "guidance" | "attention" | "runtime";
  targetSection?: string;
  targetSubTab?: PipelineSubTab;
  primaryLabel?: string;
  fileCount?: number;
}

export interface StageProgressSummary {
  stageId: string;
  substeps: StageSubstep[];
  fullyComplete: boolean;
  hasTodo: boolean;
  hasRunning: boolean;
  hasError: boolean;
  activeSubstep: StageSubstep | null;
  doneCount: number;
  totalCount: number;
}

export interface PhaseProgressSummary {
  phase: OperatorPhase;
  goal: string;
  stagesDone: number;
  stagesTotal: number;
  todoSubsteps: StageSubstep[];
  activeStageId: string | null;
}

export interface StageInfo {
  id: string;
  title: string;
  description: string;
  phase?: string;
  operator_phase?: OperatorPhase;
  status: StageStatus;
  incomplete_reason?: string;
  artifacts?: string[];
  editable?: string[];
  artifacts_present?: string[];
  artifacts_committed?: string[];
  artifacts_staged?: string[];
  artifacts_lifecycle?: Record<string, string>;
  artifacts_status?: Record<string, "pending" | "partial" | "complete" | "staged" | "n_a">;
  outputs_view?: Array<{
    path: string;
    label: string;
    status: string;
    phase: string;
    kind: string;
    sufficiency_status?: string;
  }>;
  stage_output_mode?: string;
  stage_visibility?: "visible" | "hidden";
  handoff_paths?: string[];
  audio_outputs_present?: string[];
  api_providers?: string[];
  guidance?: StageGuidance;
  /** True when this stage belongs to a second refinement pass over earlier output. */
  refinement_pass?: boolean;
  /** Id of the stage this refinement pass revisits, if applicable. */
  pass_of?: string;
  skip_reason?: string;
}

/** Operator-facing agenda for a refinement pass — see docs Refinement Pass plan. */
export interface RefinementAgenda {
  phase?: "draft" | "confirm";
  tape_character?: string[];
  eligible_classes?: string[];
  ineligible_classes?: Array<{ class_id: string; reason?: string }>;
  succession_hints?: string[];
  policy_pack_id?: string;
  prior_bias_applied?: boolean;
  north_star_notes?: string;
}

/** Point-in-time listener outcome snapshot — understanding/listener_outcome_trajectory.json. */
export interface ListenerOutcomeTrajectory {
  run_id?: string;
  points?: Array<{
    milestone: string;
    at: string;
    payload?: unknown;
  }>;
}

/** L1 gate decision for one refinement pass — see refinement_gate.py. */
export interface RefinementPassDecision {
  pass_id: string;
  cfi_id?: string;
  agenda_class?: string;
  status: "activate" | "skip";
  gate?: string;
  rationale?: string;
  reason_code?: string;
  decided_at?: string;
  input_hash?: string;
  signals?: Record<string, unknown>;
}

/** understanding/refinement_plan.json — see refinement_gate.py::load_plan. */
export interface RefinementPlan {
  run_id?: string;
  schema_version?: number;
  passes: RefinementPassDecision[];
  updated_at?: string;
}

/** Best-known artifact for a refinement domain — see refinement_champion.py. */
export interface RefinementChampionEntry {
  domain: string;
  artifact_paths: string[];
  score_vector: Record<string, number>;
  source?: string;
  updated_at?: string;
}

/** Path-only reference to an evidence packet — opened read-only via openArtifactInEditor. */
export interface RefinementEvidencePacketRef {
  pass_id: string;
  path: string;
}

/** understanding/refinement_cascade.json — downstream invalidation after an accepted candidate. */
export interface RefinementCascade {
  at?: string;
  line_ids_changed?: string[];
  line_ids_dropped?: string[];
  stages_to_invalidate?: string[];
  g1_synth_line_ids?: string[];
  remix_after_edl?: boolean;
}

/** Lightweight story snapshot — thesis / chapters / host lines — kept read-only. */
export interface RefinementBible {
  thesis?: string;
  chapters?: string[];
  host_lines?: string[];
}

/** understanding/gap_framing_recompose.json accept record — see refinement_accept.py. */
export interface RefinementRecomposeAccept {
  accepted: boolean;
  reason_code: string;
  delta?: {
    kept?: string[];
    rewritten?: string[];
    added?: string[];
    dropped?: string[];
    meaningful?: boolean;
  };
  champion_scores?: Record<string, number>;
  candidate_scores?: Record<string, number>;
  orphans?: number;
}

/** understanding/gap_framing_recompose.json — last recompose attempt's decisions + accept verdict. */
export interface RefinementRecomposeDoc {
  decisions?: Array<{ line_id: string; action: string; reason: string }>;
  accept?: RefinementRecomposeAccept;
  input_hash?: string;
}

/** Response shape for GET /api/runs/{run_id}/refinement — see refinement_routes.py. */
export interface RefinementSummary {
  agenda?: RefinementAgenda | null;
  plan?: RefinementPlan | null;
  champion?: Record<string, RefinementChampionEntry>;
  evidence_packets?: RefinementEvidencePacketRef[];
  cascade?: RefinementCascade | null;
  listener_outcome_trajectory?: ListenerOutcomeTrajectory | null;
  bible?: RefinementBible;
  /** Preview tags (confusing/dull/redundant) — advisory only. */
  preview_annotations?: Array<{ line_id?: string; tag: string; note?: string }> | null;
}

export interface ReuseCandidate {
  run_id: string;
  updated_at?: string | null;
  execution_number?: number | null;
  paths: string[];
  source_audio_hash?: string;
  source_audio_hash_short?: string;
  hash_in_run_id?: string | null;
  same_source_audio?: boolean;
  match_kind?: "hash" | null;
}

export interface JobState {
  status?: string;
  mode?: string;
  stage?: string;
  current_stage?: string;
  stage_index?: number;
  stage_total?: number;
  stages_planned?: string[];
  stages_done?: string[];
  parent_stage?: string;
  stage_progress?: Array<{ id: string; status: string }>;
  message?: string;
  updated_at?: string;
  /** Intra-stage checkpoint (e.g. gap 45/389 during disfluency extract). */
  phase?: string;
  step_index?: number;
  step_total?: number;
  error?: string;
  traceback?: string;
  last_error?: {
    message: string;
    stage?: string | null;
    traceback_excerpt?: string | null;
  };
  missing_api_providers?: string[];
  needs_api_consent?: boolean;
  preclean_warnings?: Array<{ checkpoint: string; stage: string }>;
  needs_stage_reuse?: boolean;
  reuse_candidates?: ReuseCandidate[];
  awaiting_write_approval?: boolean;
  pending_write_stage?: string;
  pending_write_paths?: string[];
  /** Structured gate id when status=gate (G-01) — prefer over message substring hacks. */
  gate?: string;
  itr_blocking_count?: number;
  can_fix_all?: boolean;
  bridge_eligible?: boolean;
  itr_open_blocking?: number;
  sufficiency_blocking?: number;
  lifecycle_phase?: string;
  /** Server defers visible needs_clarification while the pipeline lock is held. */
  clarification_pending?: boolean;
}

export interface RunData {
  run_id: string;
  /** Pillar A ESR from GET /api/runs/{id} */
  execution_status?: ExecutionStatusSummary;
  working_dir?: string;
  snapshot_version?: number;
  execution_number?: number;
  immediate_previous_run_id?: string | null;
  meta?: RunMeta;
  handoff_ack?: Record<string, string>;
  sfx_generated_assets?: Array<{ asset_id: string; path: string }>;
  journey?: JourneyState;
  blocking?: JourneyBlocking;
  transcript_review_pending?: boolean;
  transcript_review_clear?: boolean;
  profile_verified?: boolean;
  profile_gate_pending?: boolean;
  profile_ready_for_review?: boolean;
  story_board_ready?: boolean;
  timeline_ready?: boolean;
  g1_missing?: string[];
  g1_clear?: boolean;
  g1_optional?: boolean;
  operator_gates?: Record<
    string,
    {
      gate_id?: string;
      open?: boolean;
      severity?: string;
      operator_must_act?: boolean;
      stage_status?: string;
      blocks_journey?: boolean;
      ui_mode?: string;
      message?: string;
      automation?: {
        owner?: string;
        active?: boolean;
        action?: string;
        state?: string;
      };
    }
  >;
  resilience?: {
    quality_first?: boolean;
    open_escalations?: Array<{
      stage_id: string;
      failed_invariant: string;
      recommended_option: string;
      resume_stage?: string;
      options?: Array<{ id: string; label: string }>;
      status?: string;
    }>;
    order_lock?: {
      revision?: number;
      order_content_hash?: string;
      created_by?: string;
    } | null;
    suggest_delivery_resume?: string | null;
    report?: Record<string, unknown> | null;
  };
  thrash?: {
    active?: boolean;
    fail_class?: string;
    pin?: string;
    hit_count?: number;
    window_sec?: number;
    stage?: string;
    detected_at?: string;
  } | null;
  delivery_pin?: {
    from_stage?: string;
    intent?: string;
    reason?: string;
    source?: string;
  } | null;
  wasted_work?: {
    events?: Array<{
      event?: string;
      stage?: string;
      ts?: string;
      detail?: Record<string, unknown>;
    }>;
    counts?: Record<string, number>;
  } | null;
  g1_5_preview_pickup_pending?: string[];
  g1_5_preview_pickup_clear?: boolean;
  pickup_speaker_pending?: boolean;
  gap_fill_mode?: "active" | "skipped" | "pending";
  gap_framing_enabled?: boolean;
  gap_framing_decision_pending?: boolean;
  llm_recommended_framing?: string | null;
  llm_framing_rationale?: string | null;
  pipeline_mode?: { mode?: string; decided_by?: string; reason_codes?: string[] } | null;
  gap_vo_delivery?: "chatterbox" | "record" | null;
  gap_delivery_pending?: boolean;
  voice_reference_pending?: boolean;
  voice_reference_approved?: boolean;
  chatterbox_runtime_available?: boolean;
  synthesis_fallback_notice?: string | null;
  gap_fill_skip_reason?: string | null;
  flow_adaptation?: FlowAdaptation | null;
  nle_dirty?: boolean;
  analysis_complete?: boolean;
  job?: JobState;
  refinement_agenda?: RefinementAgenda;
  listener_outcome_trajectory?: ListenerOutcomeTrajectory;
  refinement_plan?: RefinementPlan | null;
  refinement_champion?: Record<string, RefinementChampionEntry>;
  refinement_evidence_packets?: RefinementEvidencePacketRef[];
  refinement_cascade?: RefinementCascade | null;
  stages: StageInfo[];
  log_tail?: LogEntry[];
  llm_verification_alerts?: Array<{
    stage_key?: string;
    interaction_id?: string;
    errors?: string[];
    path?: string;
    task_kind?: string;
  }>;
  segment_lineage_warnings?: string[];
}

export interface RunMeta {
  execution_number?: number;
  input_audio_path?: string;
  source_audio_hash?: string;
  source_audio_hash_short?: string;
  updated_at?: string;
  run_mode?: "manual" | "full-auto" | "partially-accelerated" | string;
  full_auto?: boolean;
  partial_auto?: boolean;
  partial_auto_driver_active?: boolean;
  partial_auto_complete?: boolean;
  /** Sticky operator halt from delivery guardrails / thrash. */
  needs_operator?: boolean;
  needs_operator_stage?: string;
  needs_operator_reason?: string;
  g_publish_pending?: boolean;
  g_publish_skipped?: boolean;
  g_publish_cleared?: boolean;
  homunculus_version?: string;
  homunculus_kind?: "original_pipeline" | "homunculus" | string;
  podcast_id?: string;
  podcast_title?: string;
  operator_phase?: OperatorPhase;
  journey_milestones?: Record<string, boolean>;
  preview_listened_at?: string;
  audio_preclean?: {
    offered_at?: string[];
    enabled?: boolean;
    scope?: string;
    decisions?: Array<{
      checkpoint: string;
      action: string;
      scope?: string;
      at?: string;
    }>;
  };
  qc_summaries?: Record<
    string,
    {
      passed: boolean;
      strict?: boolean;
      status?: string;
      errors?: string[];
      failed_checks?: string[];
      blocking?: boolean;
      /** Explicit false = non-advisory (blocking) gate even when blocking is unset. */
      advisory?: boolean;
      message?: string;
      /** listen_delight shape */
      overall?: number;
      failed_dimensions?: string[];
      [key: string]: unknown;
    }
  >;
  disfluency_restore?: { enabled?: boolean };
  sfx_listen_results?: SfxListenResult[];
  post_listen_gate_state?: {
    mode?: "soft" | "warn" | "block_mix";
    blocked_assets?: string[];
    updated_at?: string;
  };
  stage_reuse?: Record<
    string,
    {
      action: string;
      source_run_id?: string;
      at?: string;
      /** Set once the reused artifacts were copied into this run. */
      applied_at?: string;
    }
  >;
  /** True after transcript reuse accept until operator saves the edit interstitial. */
  transcript_reuse_pending_edit?: boolean;
  gap_fill_mode?: "active" | "skipped" | "pending";
  gap_fill_skip_reason?: string | null;
  pending_write_approval?: Record<
    string,
    {
      paths?: string[];
      created_at?: string;
    }
  >;
}

export interface SfxListenResult {
  asset_id: string;
  result: "pass" | "fail";
  at: string;
  note?: string;
}

export interface BoundaryEdgeEvidence {
  overall?: number;
  grade?: "high" | "medium" | "low" | "reject" | string;
  selected_ms?: number;
  candidate_ms?: number;
  signals?: Record<string, number>;
  reasons?: string[];
  repaired?: boolean;
  repair_action?: string;
  original_ms?: number;
}

export interface TimelineSegment {
  segment_id?: string;
  _nle_label?: string;
  start_ms: number;
  end_ms: number;
  type?: string;
  speaker_role?: string;
  text?: string;
  _mark_redo?: boolean;
  _excluded?: boolean;
  _exclude_reason?: string;
  _omit_recovery?: string;
  _manifest_start_ms?: number;
  _manifest_end_ms?: number;
  topic_tags?: string[];
  flags?: string[];
  boundary_confidence?: number;
  edge_grade?: "high" | "medium" | "low" | "reject" | string;
  start_edge?: BoundaryEdgeEvidence;
  end_edge?: BoundaryEdgeEvidence;
}

export interface VoLine {
  line_id: string;
  targets_segment_id: string;
  text: string;
  gap_type?: string;
  suggested_tone?: string;
  voice_speaker_id?: string;
  act_context?: number;
  post_preview?: boolean;
  post_preview_satisfied?: boolean;
  delivery?: string;
  line_category?: string;
  recorded_file?: string | null;
  /** "operator" lines are pinned — they survive a Pass 2 recompose as long as their target segment is kept. */
  origin?: "operator" | "llm" | string;
}

export interface TbiyConformanceElement {
  id?: string;
  presence?: string;
  action?: string;
  rationale?: string;
}

export interface TbiyConformance {
  active?: boolean;
  summary_plain?: string;
  score?: {
    ratio?: number;
    applied?: number;
    bridged?: number;
    soft?: number;
    collapsed?: number;
    deferred?: number;
    total?: number;
  };
  modes?: {
    five_act_mode?: "full" | "soft" | "collapsed" | string;
    moat_mode?: "require" | "soft" | "defer" | string;
    vo_bridge_priority?: "high" | "normal" | "low" | string;
  };
  elements?: TbiyConformanceElement[];
}

export interface FlowAdaptation {
  topology_class?: string;
  production_style?: string;
  pickup_eligible_speaker_id?: string;
  summary_plain?: string;
  ranking_weights?: Record<string, number>;
  five_act_mode?: string;
  moat_mode?: string;
  vo_bridge_priority?: string;
  tbiy_conformance?: TbiyConformance;
  operator_overrides?: {
    topology_confirmed?: boolean;
    pickup_speaker_confirmed?: boolean;
    segmentation_granularity?: string | null;
    force_resegment?: boolean;
  };
}

export interface NleState {
  sequence_order?: string[];
  segment_overrides?: Record<string, Record<string, unknown>>;
  playhead_ms?: number;
  zoom?: number;
  markers?: Array<Record<string, unknown>>;
}

export type TimelineMode = "source" | "assembly";

export interface AssemblySpeechClip {
  type: "speech";
  segment_id: string;
  timeline_start_ms: number;
  duration_ms: number;
  source_start_ms: number;
  source_end_ms: number;
  text?: string;
  speaker_role?: string;
  segment_type?: string;
}

export interface AssemblyVoClip {
  type: "vo_pickup";
  line_id: string;
  targets_segment_id: string;
  placement?: string;
  timeline_start_ms: number;
  duration_ms: number;
  recorded_file?: string | null;
  source_path?: string | null;
}

export interface AssemblyTransitionClip {
  type: "transition";
  after_segment_id?: string;
  before_segment_id?: string;
  timeline_start_ms: number;
  duration_ms: number;
  text?: string;
}

export interface AssemblyDisfluencyClip {
  type: "disfluency";
  event_id?: string;
  segment_id?: string;
  timeline_start_ms: number;
  duration_ms: number;
  source_start_ms?: number;
  source_end_ms?: number;
  source_path?: string | null;
  text?: string;
}

export type AssemblyClip =
  | AssemblySpeechClip
  | AssemblyVoClip
  | AssemblyTransitionClip
  | AssemblyDisfluencyClip;

export interface AssemblyChapter {
  title: string;
  anchor_segment_id: string;
  timeline_start_ms: number;
}

export interface AssemblyTimelineData {
  ready: boolean;
  reason?: string;
  timeline_duration_ms?: number;
  ordered_segment_ids?: string[];
  clips?: AssemblyClip[];
  chapters?: AssemblyChapter[];
  warnings?: {
    missing_vo_files?: string[];
    gap_targets_not_in_selection?: string[];
  };
  preview_audio?: string | null;
}

export interface WaveformPeaksData {
  source_path: string;
  window_ms: number;
  duration_ms: number;
  peaks: Array<{ t_ms: number; peak: number }>;
}

export interface TimelineData {
  duration_ms: number;
  segments: TimelineSegment[];
  vo_lines: VoLine[];
  nle: NleState | null;
  normalized_audio?: string | null;
  boundary_review_queue?: {
    item_count?: number;
    low_confidence_threshold?: number;
    items?: Array<{
      item_id?: string;
      segment_id?: string;
      edge?: string;
      time_ms?: number;
      overall?: number;
      grade?: string;
      kind?: string;
      reasons?: string[];
      needs_review?: boolean;
    }>;
  } | null;
}

export interface TranscriptReviewChunk {
  chunk_id: string;
  rank?: number;
  confidence?: number;
  start_ms: number;
  end_ms: number;
  clip_start_ms?: number;
  clip_end_ms?: number;
  speaker_id?: string;
  text?: string;
  corrected_text?: string;
  clip_path?: string;
  /** Server: review clip WAV exists on disk. */
  clip_ready?: boolean;
  reviewed?: boolean;
}

export interface TranscriptReviewState {
  chunks: TranscriptReviewChunk[];
  pending_count?: number;
  low_confidence_threshold?: number;
  ready?: boolean;
}

export interface TranscriptFocusRange {
  start_ms: number;
  end_ms: number;
  label?: string;
}

export interface TranscriptWord {
  text: string;
  start_ms: number;
  end_ms: number;
  speaker_id?: string;
  confidence?: number;
  corrected?: boolean;
}

export interface TranscriptSpeaker {
  id: string;
  role?: string;
}

export interface TranscriptState {
  ready?: boolean;
  text?: string;
  words: TranscriptWord[];
  duration_ms?: number;
  speakers?: TranscriptSpeaker[];
  audio_path?: string | null;
  low_confidence_threshold?: number;
  review_applied_at?: string;
}

export interface AnalysisState {
  interview_identity?: {
    title?: string;
    one_line_summary?: string;
  };
  narrative?: { thesis?: string; strategic_moat_concept?: string };
  themes?: Array<{
    id?: string;
    label?: string;
    summary?: string;
    segment_ids?: string[];
    confidence?: number;
    sources?: string[];
  }>;
  major_questions?: Array<{ question?: string } | string>;
  style?: {
    tone?: string;
    tone_class?: string;
    format_class?: string;
    format_notes?: string;
    pacing?: string;
    interviewer_style?: string;
    interviewee_style?: string;
  };
  operator_notes?: string;
  meta?: {
    operator_verified?: boolean;
    operator_locked_fields?: string[];
    production_style?: string;
  };
}

export interface AnalysisProfileResponse {
  analysis_state: AnalysisState;
  operator_verified?: boolean;
  completion?: { blockers?: string[] };
}

export interface SfxPromptRow {
  asset_id?: string;
  role?: string;
  duration_seconds?: number;
  prompt_influence?: number;
  cfg_strength?: number;
  num_steps?: number;
  seed?: number;
  mmaudio_variant?: string;
  mmaudio_qa_verdict?: string;
  mmaudio_qa_action?: string;
  regression_notes?: string;
  sfx_prompt?: string;
  negative_prompt?: string;
}

export type SfxBlockReasonKind = "g1_5" | "qa_fail" | "spend" | "venv";

export interface SfxBlockReason {
  kind: SfxBlockReasonKind;
  message: string;
  asset_ids?: string[];
}

export interface MmaudioQaRow {
  asset_id?: string;
  verdict?: string;
  reasons?: string[];
  action?: string;
  generation_status?: string;
  theme_fit_score?: number;
  semantic_qa_verdict?: string;
  semantic_qa_skipped_reason?: string;
  semantic_similarity?: number;
  spectral_bucket_match?: boolean;
  recommended_action?: string;
  suggested_trim_ms?: number;
  suggested_level_db_delta?: number;
  suggested_crossfade_ms?: number;
}

export interface SfxPromptsResponse {
  path?: string;
  prompts: SfxPromptRow[];
  listen_results?: Array<Record<string, unknown>>;
  generated_assets?: string[];
  mmaudio_qa?: { version?: number; assets?: MmaudioQaRow[] };
  block_reasons?: (string | SfxBlockReason)[];
  sonic_context?: SonicContextData | null;
  generation_meta?: Record<string, Record<string, unknown>>;
  review?: {
    approved?: boolean;
    approved_by?: string;
    approved_at?: string;
  };
  review_required?: boolean;
  can_generate?: boolean;
  warnings?: string[];
}

export interface PlacementAdjustmentsArtifact {
  version?: number;
  adjustments?: Array<{
    asset_id?: string;
    action?: string;
    reason?: string;
    suggested_level_db_delta?: number;
    suggested_crossfade_ms?: number;
    provenance?: {
      rule_id?: string;
      source_artifact?: string;
      detail?: string;
    };
    scenario_override?: boolean;
  }>;
}

export interface SonicContextTag {
  tag_id: string;
  kind?: string;
  keywords?: string[];
  segment_ids?: string[];
  emotional_valence?: string;
  confidence?: number;
  provenance?: string[];
}

export interface SonicContextData {
  version?: number;
  sonic_context_hash?: string;
  scenario?: {
    atlas_bucket?: string;
    format_class?: string;
    tone_class?: string;
  };
  tag_registry?: SonicContextTag[];
  mix_policy?: {
    underscore_policy?: string;
    adaptive_max_assets_flow1?: number;
    adaptive_max_assets_flow2?: number;
    stinger_cap_per_minute?: number;
  };
  avoid_hard?: string[];
}

export interface LlmRoutingResponse {
  attempts: LlmRoutingAttempt[];
}

export interface ResilienceReportSummary {
  stage_key?: string;
  artifact_path?: string;
  kept_paths?: string[];
  stripped?: Array<{ path?: string; reason?: string; removed_value?: unknown }>;
  generated?: Array<{ path?: string; source?: string; value?: unknown }>;
  summary?: string;
  artifact_mass_score?: number;
}

export interface InvestigationPatchBody {
  status?: string;
  resolution_note?: string;
}

export interface LlmRoutingAttempt {
  stage: string;
  file?: string;
  task_kind?: string;
  attempt?: number;
  verdict?: string;
  arbiter_verdict?: string;
  arbiter_reason?: string;
  shard_count?: number;
  truncation_flags?: string[];
  shard_plan_source?: string;
  routed_via_collate?: boolean;
  model_tier?: string;
  model_id?: string;
  context_chars?: number;
  schema_errors?: string[];
  deterministic_lint_errors?: string[];
  persist_action?: "none" | "partial" | "full";
  resilience_report?: ResilienceReportSummary;
  primary_attempt_count?: number;
  budget_remaining_primary?: number;
  stuck_count?: number;
}

export interface ExecuteBody {
  mode:
    | "stage"
    | "analysis"
    | "analysis_until_g0"
    | "delivery"
    | "delivery_until_preview"
    | "delivery_polish"
    | "nle_apply";
  stage?: string;
  from_stage?: string;
  until_stage?: string;
  nle_full_refresh?: boolean;
  nle_apply_mode?: "trim_only" | "structural" | "full_refresh";
  api_consents?: Record<string, boolean>;
}

export interface PrecleanOffer {
  checkpoint: string;
  scope: string;
  prompt: string;
}

export type AppTab = "start" | "executions" | "pipeline" | "logs";
export type PipelineSubTab =
  | "stage"
  | "story"
  | "timeline"
  | "profile"
  | "files"
  | "llm_calls"
  | "volley_memory";

export type WorkflowStepId = "start" | OperatorPhase;

export type ActivityKind =
  | "idle"
  | "no_run"
  | "running"
  | "gate"
  | "error"
  | "interrupted"
  | "handoff"
  | "write_approval"
  | "reuse"
  | "blocked"
  | "ready"
  | "done";

/** Activity log panel stream identifiers (Live | This step | All). */
export type LogStreamTab = "live" | "step" | "all";

/** Alias for stream tab ids used in filters and session persistence. */
export type LogStream = LogStreamTab;

export interface LogFilterPreset {
  stage?: string;
  level?: string;
  stream?: LogStreamTab;
  scrollToError?: boolean;
}

export interface LiveStatus {
  activityKind: ActivityKind;
  headline: string;
  subline: string;
  pipelineStep: {
    number: number | null;
    total: number;
    title: string;
    phaseLabel: string;
  } | null;
  workflowPhase: {
    index: number;
    total: number;
    id: WorkflowStepId;
    label: string;
  };
  runningStageId: string | null;
  focusStageId: string | null;
  primaryLabel: string | null;
  primaryDisabled: boolean;
  secondaryLabel: string | null;
  onPrimary: (() => void) | null;
  onSecondary: (() => void) | null;
  errorCount: number;
  jobProgress: { index: number; total: number } | null;
  lastError: JobState["last_error"] | null;
}

export interface SessionActive {
  run_id?: string;
  selected_stage_id?: string | null;
  active_step_id?: string | null;
  active_tab?: AppTab;
  pipeline_sub_tab?: PipelineSubTab;
  source_locked?: boolean;
  input_audio_path?: string;
  updated_at?: string;
  activity_log_tab?: LogStreamTab;
  activity_log_collapsed?: boolean;
  pipeline_collapsed_stages?: string[];
  pipeline_expanded_done_stages?: string[];
  pipeline_filter_needs_you?: boolean;
  active_client_instance_id?: string | null;
  ui_revision?: number;
}

export interface OpenRunOptions {
  quiet?: boolean;
  force?: boolean;
  selectedStageId?: string | null;
  /** After run.sh restart, land on stage 1 before the one-time needs-you redirect. */
  preferFirstStage?: boolean;
  activeTab?: AppTab;
  pipelineSubTab?: PipelineSubTab;
}

export interface VolleyEntry {
  entry_id: string;
  kind: string;
  role: string;
  content: string;
  source?: {
    stage_key?: string;
    attempt?: number;
    task_kind?: string;
    call_id?: string;
    llm_call_path?: string;
    investigation_id?: string;
  };
  tags?: string[];
  scope?: { consumer_stages?: string[]; investigation_kinds?: string[] };
  status: string;
  char_count?: number;
  operator_edited?: boolean;
}

export interface ContextIndexSummary {
  index: {
    schema_version?: number;
    volley_entries?: VolleyEntry[];
    stage_plans?: Record<string, unknown>;
    padding_rules?: Record<string, unknown>;
  };
  stats: {
    total: number;
    by_kind: Record<string, number>;
    by_status: Record<string, number>;
  };
  rebuild_stats?: Record<string, number>;
}

export interface CoherenceRisk {
  risk_id: string;
  kind: "topic_drift" | "claim_contradiction" | "missing_callback";
  time_ms?: number;
  window_id?: string | null;
  theme_id?: string | null;
  claim_id?: string | null;
  confidence?: number;
  blocking?: boolean;
  evidence?: Record<string, unknown>;
  status?: "open" | "resolved";
}

export interface CoherenceReport {
  schema_version?: number;
  gate?: {
    min_duration_ms?: number;
    activated?: boolean;
    duration_ms?: number;
  };
  risks?: CoherenceRisk[];
  summary?: {
    topic_drift_count?: number;
    claim_contradiction_count?: number;
    missing_callback_count?: number;
    phase?: string;
  };
}

export interface LlmCallSummary {
  path: string;
  call_id?: string;
  label?: string;
  stage_key?: string;
  attempt?: number;
  sequence?: number;
  task_kind?: string;
  importance?: "high" | "medium" | "low";
  provider?: string;
  model_id?: string;
  model_tier?: string;
  recorded_at?: string;
  context_chars?: number;
  truncation_flags?: string[];
  turn_count?: number;
  has_system?: boolean;
  load_error?: boolean;
  verification_ok?: boolean;
  interaction_id?: string;
}

export interface LlmCallVolleyTurn {
  role: "user" | "assistant";
  content: string;
}

export interface LlmCallRecord {
  schema_version?: number;
  call_id?: string;
  label?: string;
  stage_key?: string;
  attempt?: number;
  sequence?: number;
  task_kind?: string;
  importance?: string;
  model_id?: string;
  model_tier?: string;
  recorded_at?: string;
  volley?: {
    system_prompt?: string;
    turns?: LlmCallVolleyTurn[];
  };
  response?: {
    raw_content?: string;
    parsed_envelope?: Record<string, unknown>;
  };
  request?: { messages?: LlmCallVolleyTurn[] };
  truncation_flags?: string[];
  context_chars?: number;
  links?: Record<string, string>;
  interaction_id?: string;
  verification?: {
    ok?: boolean;
    errors?: string[];
    schema_name?: string;
    interaction_id?: string;
  };
  _gui?: {
    path?: string;
    openai_messages?: LlmCallVolleyTurn[];
  };
}

export interface LlmCallsIndex {
  run_id: string;
  call_count: number;
  calls: LlmCallSummary[];
  tree: Record<string, Record<string, LlmCallSummary[]>>;
  stages: string[];
  verification_alerts?: Array<{
    stage_key?: string;
    interaction_id?: string;
    errors?: string[];
    path?: string;
    task_kind?: string;
  }>;
}

/** @deprecated use AppTab */
export type ViewName = "home" | "workspace";
