export type LogLevel = "info" | "success" | "warning" | "error" | "action";

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
  disfluency_extract_enabled?: boolean;
  disfluency_restore_enabled?: boolean;
  api_consent_persist?: boolean;
  journey_ui?: {
    enabled?: boolean;
    intent_at_start?: boolean;
    phase_sidebar?: boolean;
    story_board?: boolean;
    unified_preclean_drawer?: boolean;
    express_flow1?: boolean;
    journey_log_filter?: boolean;
    require_preview_listen?: boolean;
    enable_stage_reuse_offers?: boolean;
    require_write_approval_per_stage?: boolean;
  };
  /** Stage ids that may show LLM routing summary — from web/stages.py */
  llm_routing_stage_ids?: string[];
}

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
  selected_flow?: string;
  progress?: { done: number; total: number };
  last_log?: LogEntry;
  job_status?: string;
  last_stage?: string;
  outputs?: string[];
}

export type StageStatus =
  | "done"
  | "pending"
  | "action_required"
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
  | "execute";

export interface JourneyBlocking {
  blocked?: boolean;
  reason?: string | null;
  message?: string;
  stage_id?: string | null;
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
  flow_intent?: string | null;
  selected_flow?: string | null;
  next_action: string;
  blocking: JourneyBlocking;
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
  sound_labels?: string[];
  phase_guidance?: Record<string, PhaseGuidance>;
}

export type GuidanceItemStatus = "todo" | "done" | "waiting";

export interface GuidanceItem {
  id: string;
  label: string;
  status: GuidanceItemStatus;
  stage_id?: string;
  action?: string;
  kind?: string;
  from_stage_id?: string;
  from_stage_title?: string;
}

export interface StageGuidance {
  phase_label: string;
  prerequisites: GuidanceItem[];
  actions: GuidanceItem[];
  unlocks: string;
  artifact_checks?: Array<{
    path: string;
    label: string;
    status: GuidanceItemStatus;
  }>;
}

export interface PhaseGuidance {
  goal: string;
  actions: GuidanceItem[];
  progress?: { done: number; total: number } | null;
}

export interface StageInfo {
  id: string;
  title: string;
  description: string;
  phase?: string;
  operator_phase?: OperatorPhase;
  status: StageStatus;
  artifacts?: string[];
  editable?: string[];
  artifacts_present?: string[];
  artifacts_status?: Record<string, "pending" | "partial" | "complete">;
  handoff_paths?: string[];
  audio_outputs_present?: string[];
  api_providers?: string[];
  guidance?: StageGuidance;
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
  message?: string;
  updated_at?: string;
  error?: string;
  traceback?: string;
  last_error?: {
    message: string;
    stage?: string | null;
    traceback_excerpt?: string | null;
  };
  missing_api_providers?: string[];
  preclean_warnings?: Array<{ checkpoint: string; stage: string }>;
  needs_stage_reuse?: boolean;
  reuse_candidates?: ReuseCandidate[];
  awaiting_write_approval?: boolean;
  pending_write_stage?: string;
  pending_write_paths?: string[];
}

export interface RunData {
  run_id: string;
  meta?: RunMeta;
  handoff_ack?: Record<string, string>;
  elevenlabs_generated_assets?: Array<{ asset_id: string; path: string }>;
  selected_flow?: string;
  flow_intent?: string;
  display_flow?: string;
  journey?: JourneyState;
  blocking?: JourneyBlocking;
  transcript_review_pending?: boolean;
  transcript_review_clear?: boolean;
  disfluency_review_pending?: boolean;
  disfluency_review_clear?: boolean;
  profile_verified?: boolean;
  profile_gate_pending?: boolean;
  profile_ready_for_review?: boolean;
  g1_missing?: string[];
  g1_clear?: boolean;
  analysis_complete?: boolean;
  job?: JobState;
  stages: StageInfo[];
  log_tail?: LogEntry[];
}

export interface RunMeta {
  execution_number?: number;
  input_audio_path?: string;
  source_audio_hash?: string;
  source_audio_hash_short?: string;
  updated_at?: string;
  selected_flow?: string;
  flow_intent?: string;
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
    { passed: boolean; strict?: boolean; errors?: string[] }
  >;
  disfluency_restore?: { enabled?: boolean };
  elevenlabs_listen_results?: ElevenLabsListenResult[];
  stage_reuse?: Record<
    string,
    {
      action: string;
      source_run_id?: string;
      at?: string;
    }
  >;
}

export interface ElevenLabsListenResult {
  asset_id: string;
  result: "pass" | "fail";
  at: string;
  note?: string;
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
  _manifest_start_ms?: number;
  _manifest_end_ms?: number;
  topic_tags?: string[];
  flags?: string[];
}

export interface VoLine {
  line_id: string;
  targets_segment_id: string;
  text: string;
  gap_type?: string;
  delivery?: string;
  recorded_file?: string | null;
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
}

export interface TranscriptReviewChunk {
  chunk_id: string;
  rank?: number;
  confidence?: number;
  start_ms: number;
  end_ms: number;
  speaker_id?: string;
  text?: string;
  corrected_text?: string;
  clip_path?: string;
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
  narrative?: { thesis?: string };
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
  meta?: { operator_verified?: boolean; operator_locked_fields?: string[] };
}

export interface AnalysisProfileResponse {
  analysis_state: AnalysisState;
  operator_verified?: boolean;
  completion?: { blockers?: string[] };
}

export interface ElevenLabsPromptRow {
  asset_id?: string;
  role?: string;
  duration_seconds?: number;
  prompt_influence?: number;
  elevenlabs_prompt?: string;
  negative_prompt?: string;
}

export interface ElevenLabsPromptsResponse {
  path?: string;
  prompts: ElevenLabsPromptRow[];
  listen_results?: Array<Record<string, unknown>>;
  generated_assets?: string[];
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
  }>;
}

export interface LlmRoutingResponse {
  attempts: LlmRoutingAttempt[];
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
  primary_attempt_count?: number;
  budget_remaining_primary?: number;
  stuck_count?: number;
}

export interface ExecuteBody {
  mode:
    | "stage"
    | "analysis"
    | "analysis_until_g0"
    | "flow1"
    | "flow1_until_preview"
    | "flow1_polish"
    | "flow2"
    | "flow3"
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
  active_tab?: AppTab;
  pipeline_sub_tab?: PipelineSubTab;
  source_locked?: boolean;
  input_audio_path?: string;
  updated_at?: string;
  activity_log_tab?: LogStreamTab;
  activity_log_collapsed?: boolean;
}

export interface OpenRunOptions {
  quiet?: boolean;
  force?: boolean;
  selectedStageId?: string | null;
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

export interface StoryBoardData {
  analysis_state: AnalysisState;
  investigation_queue: Record<string, unknown>;
  content_brief: Record<string, unknown>;
  narrative_plan?: Record<string, unknown> | null;
  source_acoustic_profile?: Record<string, unknown> | null;
  value_features?: Record<string, unknown> | null;
  operator_verified?: boolean;
}

export interface AudioQualityState {
  audio_preclean?: Record<string, unknown>;
  checkpoints: Array<{ id: string; acknowledged: boolean }>;
  recommended?: string | null;
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
}

/** @deprecated use AppTab */
export type ViewName = "home" | "workspace";
