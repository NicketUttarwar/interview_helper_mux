import { useMemo } from "react";
import type { ExecuteBody, RunData, StageInfo } from "../types";
import { findHandoffStage, stageTitleForId } from "../utils/checkpoint";
import { hintToExecuteBody } from "../utils/executeHint";
import { findNextRunnableStage } from "../utils/preclean";
import { resolvePipelineNav } from "../utils/pipelineNavigation";
import { resolveJobStatusContext } from "../utils/operatorStatus";
import { resolvePendingAction } from "../utils/pendingAction";
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

export function useOperatorCommand(
  run: RunData | null,
  opts: {
    jobRunning: boolean;
    selectedStageId?: string | null;
    apiGrants?: Record<string, boolean>;
    onExecute: (body: ExecuteBody) => void;
    onRunNext: () => void;
    onOpenCheckpoint: (stageId?: string) => void;
    onAcknowledgeHandoff: () => void;
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

    const journey = run.journey;
    const nextAction = journey?.next_action || "";
    const hint = journey?.execute_hint;
    const blocking = journey?.blocking ?? run.blocking;
    const handoffStage = findHandoffStage(run);
    const job = run.job;
    const pending = resolvePendingAction(run, apiGrants);

    const nextHandlers: NextActionHandlers = {
      onOpenCheckpoint,
      onExecute,
      onRunNext,
      onAcknowledgeHandoff,
      onGoPipeline,
      onGoStory,
      onGoProfile,
      onScrollPreview,
    };
    const nextClick = resolveNextActionClick(run, nextHandlers);

    const runningTitle =
      stageTitleForId(run.stages, job?.stage) ||
      (job?.stage ? job.stage.replace(/_/g, " ") : null) ||
      job?.mode ||
      "pipeline";

    if (job?.status === "interrupted") {
      return {
        kind: "error",
        statusLine: job.message || "Run interrupted — re-run the last step.",
        primaryLabel: "View logs",
        primaryDisabled: false,
        secondaryLabel: run?.journey?.execute_hint?.label || null,
        onPrimary: onGoLogs,
        onSecondary:
          run?.journey?.execute_hint && hintToExecuteBody(run.journey.execute_hint)
            ? () => onExecute(hintToExecuteBody(run.journey!.execute_hint!)!)
            : null,
        handoffStage: null,
      };
    }

    if (jobRunning || job?.status === "running" || job?.status === "running_with_warnings") {
      return {
        kind: "running",
        statusLine: job?.message || `Running: ${runningTitle}`,
        primaryLabel: "View logs",
        primaryDisabled: false,
        secondaryLabel: null,
        onPrimary: onGoLogs,
        onSecondary: null,
        handoffStage: null,
      };
    }

    if (job?.status === "error") {
      return {
        kind: "error",
        statusLine: job.message || "Last job failed — see Logs.",
        primaryLabel: "View logs",
        primaryDisabled: false,
        secondaryLabel: hint?.label && hintToExecuteBody(hint) ? hint.label : null,
        onPrimary: onGoLogs,
        onSecondary:
          hint && hintToExecuteBody(hint)
            ? () => onExecute(hintToExecuteBody(hint)!)
            : null,
        handoffStage: null,
      };
    }

    if (blocking?.blocked && blocking.message) {
      return {
        kind: "blocked",
        statusLine: blocking.message,
        primaryLabel: pending?.primaryLabel || nextAction || "Open checkpoint",
        primaryDisabled: false,
        secondaryLabel: "Pipeline",
        onPrimary: () => onOpenCheckpoint(blocking.stage_id || undefined),
        onSecondary: onGoPipeline,
        handoffStage: null,
      };
    }

    if (handoffStage) {
      return {
        kind: "handoff",
        statusLine: pending?.message || `Step done — review outputs from ${handoffStage.title}.`,
        primaryLabel: pending?.primaryLabel || "Review outputs",
        primaryDisabled: false,
        secondaryLabel: "Acknowledge & continue",
        onPrimary: () => onOpenCheckpoint(handoffStage.id),
        onSecondary: onAcknowledgeHandoff,
        handoffStage,
      };
    }

    const deliverable = journey?.deliverable;
    if (
      journey?.phase === "ship" &&
      deliverable?.kind &&
      deliverable.kind !== "none" &&
      !hint
    ) {
      return {
        kind: "done",
        statusLine: nextAction || "Deliverable ready.",
        primaryLabel: nextAction || "Open Pipeline",
        primaryDisabled: false,
        secondaryLabel: "View logs",
        onPrimary: nextClick?.onClick ?? onGoPipeline,
        onSecondary: onGoLogs,
        handoffStage: null,
      };
    }

    if (hint?.action === "checkpoint") {
      return {
        kind: "ready",
        statusLine: nextAction,
        primaryLabel: hint.label || pending?.primaryLabel || nextAction,
        primaryDisabled: false,
        secondaryLabel: null,
        onPrimary: () => onOpenCheckpoint(hint.stage_id),
        onSecondary: null,
        handoffStage: null,
      };
    }

    const body = hint ? hintToExecuteBody(hint) : null;
    if (hint && body) {
      return {
        kind: "ready",
        statusLine: nextAction,
        primaryLabel: hint.label || nextAction,
        primaryDisabled: jobRunning,
        secondaryLabel: pending?.primaryLabel || "Open checkpoint",
        onPrimary: () => onExecute(body),
        onSecondary: () => onOpenCheckpoint(pending?.stageId),
        handoffStage: null,
      };
    }

    const nav = resolvePipelineNav(run, {
      selectedStageId,
      jobRunning,
      apiGrants,
    });
    const jobCtx = resolveJobStatusContext(run, jobRunning);
    const nextRunnable = findNextRunnableStage(run.stages);

    if (nav.primaryAction === "run_next" && nextRunnable && !jobCtx.isRunning) {
      return {
        kind: "ready",
        statusLine: nav.statusLine || nextAction,
        primaryLabel: hint?.label || nextAction || `Run ${nextRunnable.title}`,
        primaryDisabled: false,
        secondaryLabel: pending?.primaryLabel || "Open checkpoint",
        onPrimary: onRunNext,
        onSecondary: () => onOpenCheckpoint(nextRunnable.id),
        handoffStage: null,
      };
    }

    if (nav.primaryAction === "handoff" && nav.handoffStage) {
      return {
        kind: "handoff",
        statusLine: nav.statusLine || nextAction,
        primaryLabel: pending?.primaryLabel || "Review outputs",
        primaryDisabled: false,
        secondaryLabel: "Acknowledge & continue",
        onPrimary: () => onOpenCheckpoint(nav.handoffStage!.id),
        onSecondary: onAcknowledgeHandoff,
        handoffStage: nav.handoffStage,
      };
    }

    if (nav.primaryAction === "checkpoint" && nav.canRunNext) {
      return {
        kind: "blocked",
        statusLine: nav.statusLine || nextAction,
        primaryLabel: pending?.primaryLabel || "Open checkpoint",
        primaryDisabled: false,
        secondaryLabel: "Pipeline",
        onPrimary: () => onOpenCheckpoint(nav.focusStageId || undefined),
        onSecondary: onGoPipeline,
        handoffStage: null,
      };
    }

    if (nextClick) {
      return {
        kind: "ready",
        statusLine: nextAction,
        primaryLabel: nextClick.label,
        primaryDisabled: nextClick.disabled ?? false,
        secondaryLabel: null,
        onPrimary: nextClick.onClick,
        onSecondary: null,
        handoffStage: null,
      };
    }

    if (nextAction) {
      return {
        kind: "ready",
        statusLine: nextAction,
        primaryLabel: nextAction,
        primaryDisabled: false,
        secondaryLabel: null,
        onPrimary: onGoPipeline,
        onSecondary: null,
        handoffStage: null,
      };
    }

    return {
      kind: "idle",
      statusLine: "Idle — select a stage or view logs.",
      primaryLabel: "Open Pipeline",
      primaryDisabled: false,
      secondaryLabel: "View logs",
      onPrimary: onGoPipeline,
      onSecondary: onGoLogs,
      handoffStage: null,
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
  ]);
}
