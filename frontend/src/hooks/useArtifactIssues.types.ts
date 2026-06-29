import type { ArtifactIssueOption } from "./useArtifactIssues";

export interface RecoveryAction {
  type: string;
  label: string;
  stage?: string;
}

export interface PropagationPlan {
  from_stage?: string;
  stale_stages?: string[];
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
  chosen?: unknown;
  auto_applied?: unknown;
}

export interface StageIssuesResponse {
  stage_id: string;
  items: ArtifactIssue[];
  open_blocking: number;
}
