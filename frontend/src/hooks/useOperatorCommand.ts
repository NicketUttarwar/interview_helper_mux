import { useMemo } from "react";
import type { AppTab, ExecuteBody, RunData, StageInfo } from "../types";
import { findHandoffStage } from "../utils/checkpoint";
import { hintToExecuteBody } from "../utils/executeHint";
import { resolveOperatorAction } from "../utils/resolveOperatorAction";
import {
  executeBodyForStage,
  invokeOperatorActionPrimary,
} from "../utils/operatorActionHandlers";
import { resolveNextActionClick, type NextActionHandlers } from "../utils/nextActionHandler";

export type CommandKind =
  | "idle"
  | "no_run"
  | "running"
  | "error"
  | "blocked"
  | "handoff"
  | "ready"
  | "done";

export interface OperatorCommandState {
  kind: CommandKind;
  statusLine: string;
  primaryLabel: string | null;
  primaryDisabled: boolean;
  secondaryLabel: string | null;
  onPrimary: (() => void) | null;
  onSecondary: (() => void) | null;
  handoffStage: StageInfo | null;
}

function modeToKind(mode: string, jobStatus?: string): CommandKind {
  if (jobStatus === "error") return "error";
  if (mode === "error") return "error";
  if (jobStatus === "interrupted") return "error";
  if (mode === "running") return "running";
  if (mode === "needs_you") return "blocked";
  if (mode === "done") return "done";
  if (mode === "locked") return "blocked";
  return "ready";
}

export function useOperatorCommand(
  run: RunData | null,
  opts: {
    jobRunning: boolean;
    selectedStageId?: string | null;
    apiGrants?: Record<string, boolean>;
    surface?: "header" | "sidebar" | "banner";
    activeTab?: AppTab;
    onExecute: (body: ExecuteBody) => void;
    onRunNext: () => void;
    onOpenCheckpoint: (stageId?: string) => void;
    onAcknowledgeHandoff: () => void;
    onApproveWrite?: (stageId: string) => void;
    onGoLogs: () => void;
    onGoStart: () => void;
    onGoPipeline: () => void;
    onGoStory?: () => void;
    onGoProfile?: () => void;
    onScrollPreview?: () => void;
  },
): OperatorCommandState {
  const {
    jobRunning,
    selectedStageId = null,
    apiGrants = {},
    onExecute,
    onRunNext,
    onOpenCheckpoint,
    onAcknowledgeHandoff,
    onGoLogs,
    onGoStart,
    onGoPipeline,
    onGoStory = onGoPipeline,
    onGoProfile = onGoPipeline,
    onScrollPreview = onGoPipeline,
  } = opts;

  return useMemo(() => {
    const empty: OperatorCommandState = {
      kind: "no_run",
      statusLine: "Start or resume an execution to continue.",
      primaryLabel: "Go to Start",
      primaryDisabled: false,
      secondaryLabel: null,
      onPrimary: onGoStart,
      onSecondary: null,
      handoffStage: null,
    };

    if (!run) return empty;

    const action = resolveOperatorAction(run, {
      selectedStageId,
      jobRunning,
      apiGrants,
    });
    const handoffStage = findHandoffStage(run);
    const hint = run.journey?.execute_hint;

    const nextHandlers: NextActionHandlers = {
      onOpenCheckpoint,
      onExecute,
      onRunNext,
      onAcknowledgeHandoff,
      onApproveWrite: opts.onApproveWrite,
      onGoPipeline,
      onGoStory,
      onGoProfile,
      onScrollPreview,
    };
    const nextClick = resolveNextActionClick(run, nextHandlers);

    const handlers = {
      openModal: (sid?: string | null) => {
        onOpenCheckpoint(sid ?? undefined);
      },
      runStage: (sid: string) => onExecute(executeBodyForStage(sid)),
      continueNext: () => onRunNext(),
      viewLogs: () => onGoLogs(),
    };

    let onPrimary: (() => void) | null = () =>
      invokeOperatorActionPrimary(action, handlers);

    let primaryLabel = action.primaryLabel;
    let primaryDisabled = action.primaryDisabled;

    if (action.mode === "running") {
      onPrimary = onGoLogs;
      primaryLabel = "View logs";
      primaryDisabled = false;
    } else if (action.mode === "error" || run.job?.status === "error") {
      onPrimary =
        action.primaryKind === "run_stage" && action.stageId
          ? () => onExecute(executeBodyForStage(action.stageId!))
          : onGoLogs;
      primaryLabel = action.primaryLabel;
      primaryDisabled = action.primaryDisabled;
    } else if (
      nextClick &&
      action.primaryKind === "none" &&
      action.mode === "idle" &&
      !action.primaryDisabled
    ) {
      onPrimary = nextClick.onClick;
      primaryLabel = nextClick.label;
      primaryDisabled = nextClick.disabled ?? false;
    } else if (action.primaryKind === "none" && hint && hintToExecuteBody(hint)) {
      onPrimary = () => onExecute(hintToExecuteBody(hint)!);
      primaryLabel = hint.label;
      primaryDisabled = false;
    }

    const secondaryLabel =
      action.secondaryLabel ??
      (action.mode === "needs_you" ? "Pipeline" : null);
    const onSecondary =
      action.secondaryKind === "view_logs"
        ? onGoLogs
        : action.mode === "needs_you"
          ? onGoPipeline
          : null;

    return {
      kind: modeToKind(action.mode, run.job?.status),
      statusLine: action.headline,
      primaryLabel,
      primaryDisabled,
      secondaryLabel,
      onPrimary,
      onSecondary,
      handoffStage,
    };
  }, [
    run,
    jobRunning,
    selectedStageId,
    apiGrants,
    onExecute,
    onRunNext,
    onOpenCheckpoint,
    onAcknowledgeHandoff,
    onGoLogs,
    onGoStart,
    onGoPipeline,
    onGoStory,
    onGoProfile,
    onScrollPreview,
    opts.onApproveWrite,
  ]);
}
