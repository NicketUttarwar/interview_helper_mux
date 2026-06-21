export type StepMode = "locked" | "idle" | "running" | "needs_you" | "done" | "error";

export type OperatorPrimaryKind =
  | "none"
  | "open_modal"
  | "run_stage"
  | "continue_next"
  | "view_logs";

export type OperatorSecondaryKind = "view_logs" | "open_logs_tab" | "redo_stage" | "skip_optional";

export interface OperatorActionProgress {
  current: number;
  total: number;
  label?: string;
}

export interface OperatorAction {
  mode: StepMode;
  stageId: string | null;
  substepId: string | null;
  headline: string;
  subline: string | null;
  primaryLabel: string;
  primaryKind: OperatorPrimaryKind;
  primaryDisabled: boolean;
  secondaryLabel?: string;
  secondaryKind?: OperatorSecondaryKind;
  progress?: OperatorActionProgress;
  blockingReason?: string;
  modalAutoOpen: boolean;
}

export interface OperatorActionContext {
  selectedStageId?: string | null;
  jobRunning?: boolean;
  apiGrants?: Record<string, boolean>;
  preferStageId?: string | null;
}

export interface ServerOperatorAction {
  mode?: StepMode;
  stage_id?: string | null;
  substep_id?: string | null;
  headline?: string;
  subline?: string | null;
  primary_label?: string;
  modal_auto_open?: boolean;
}
