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
  updated_at?: string;
  created_at?: string;
  selected_flow?: string;
  progress?: { done: number; total: number };
  last_log?: LogEntry;
  outputs?: string[];
}

export type StageStatus = "done" | "pending" | "action_required" | "locked";

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
  audio_outputs_present?: string[];
  api_providers?: string[];
}

export interface JobState {
  status?: string;
  mode?: string;
  stage?: string;
  message?: string;
  updated_at?: string;
  missing_api_providers?: string[];
  preclean_warnings?: Array<{ checkpoint: string; stage: string }>;
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
  profile_verified?: boolean;
  profile_gate_pending?: boolean;
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
  };
  qc_summaries?: Record<
    string,
    { passed: boolean; strict?: boolean; errors?: string[] }
  >;
  elevenlabs_listen_results?: ElevenLabsListenResult[];
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
    pacing?: string;
    interviewer_style?: string;
    interviewee_style?: string;
  };
  operator_notes?: string;
  meta?: { operator_verified?: boolean };
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
  prompts: ElevenLabsPromptRow[];
  review?: {
    approved?: boolean;
    approved_by?: string;
    approved_at?: string;
  };
  review_required?: boolean;
  can_generate?: boolean;
  warnings?: string[];
}

export interface LlmRoutingAttempt {
  stage: string;
  task_kind?: string;
  verdict?: string;
  shard_count?: number;
  truncation_flags?: string[];
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
    | "flow3";
  stage?: string;
  from_stage?: string;
  until_stage?: string;
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
  | "llm_calls";

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
