import type { ArtifactIssueOption } from "./useArtifactIssues";

export interface RecoveryAction {
  type: string;
  label: string;
  stage?: string;
}

export interface PropagationPlan {
  from_stage?: string;
  stale_stages?: string[];
  stage_labels?: Record<string, string>;
  change_hint?: string | null;
  tbiy_affected?: boolean;
  invalidate_from?: string | null;
  cross_errors?: string[];
  suggested_upstream_stage?: string | null;
  has_blocking?: boolean;
}

export type { ArtifactIssueOption };

export interface ArtifactIssue {
  id: string;
  stage_key: string;
  artifact_path?: string;
  json_path?: string;
  segment_id?: string;
  kind: string;
  severity: string;
  blocking?: boolean;
  message: string;
  status: string;
  repair_strategy?: string;
  options?: ArtifactIssueOption[];
  recovery_actions?: RecoveryAction[];
  suggested_upstream_stage?: string;
  recommended_choice?: unknown;
  auto_resolvable?: boolean;
  chosen?: unknown;
  auto_applied?: unknown;
}

export interface AutoResolveResult {
  outcome: string;
  stage_key: string;
  phase?: string;
  open_blocking?: number;
  resolved_count?: number;
  resolved_ids?: string[];
  failed_at?: string | null;
  warnings?: string[];
  errors?: string[];
  can_advance_pipeline?: boolean;
  downstream_job?: Record<string, unknown> | null;
  preview?: Array<{
    issue_id?: string;
    message?: string;
    segment_id?: string;
    recommended_choice?: unknown;
    auto_resolvable?: boolean;
  }>;
  attempt?: number;
  propagation_plan?: PropagationPlan | null;
}

export interface StageIssuesSummary {
  tier?: string;
  step_label?: string;
  can_fix_all?: boolean;
  preview?: AutoResolveResult["preview"];
  open_blocking?: number;
}

export interface StageIssuesResponse {
  stage_id: string;
  items: ArtifactIssue[];
  open_blocking: number;
  summary?: StageIssuesSummary;
  capabilities?: Record<string, unknown>;
}
