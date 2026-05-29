export type LogLevel = "info" | "success" | "warning" | "error" | "action";

export interface LogEntry {
  ts: string;
  level?: LogLevel;
  message: string;
  stage?: string;
  detail?: string | Record<string, unknown>;
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

export interface StageInfo {
  id: string;
  title: string;
  description: string;
  phase?: string;
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
  preclean_warnings?: Array<{ checkpoint: string; stage: string }>;
}

export interface RunData {
  run_id: string;
  meta?: RunMeta;
  handoff_ack?: Record<string, string>;
  elevenlabs_generated_assets?: Array<{ asset_id: string; path: string }>;
  selected_flow?: string;
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
  mode: "stage" | "analysis" | "flow1" | "flow2" | "flow3";
  stage?: string;
  from_stage?: string;
  api_consents?: Record<string, boolean>;
}

export interface PrecleanOffer {
  checkpoint: string;
  scope: string;
  prompt: string;
}

export type AppTab = "start" | "executions" | "pipeline" | "logs";
export type PipelineSubTab = "stage" | "timeline" | "profile" | "files";

/** @deprecated use AppTab */
export type ViewName = "home" | "workspace";
