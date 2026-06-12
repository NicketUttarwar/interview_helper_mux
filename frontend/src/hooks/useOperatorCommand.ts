import { useMemo } from "react";
import type { ExecuteBody, RunData, StageInfo } from "../types";
import { findHandoffStage, stageTitleForId } from "../utils/checkpoint";
import { hintToExecuteBody } from "../utils/executeHint";

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
    onExecute: (body: ExecuteBody) => void;
    onOpenCheckpoint: (stageId?: string) => void;
    onAcknowledgeHandoff: () => void;
    onGoLogs: () => void;
    onGoStart: () => void;
    onGoPipeline: () => void;
  },
): OperatorCommandState {
  const {
    jobRunning,
    onExecute,
    onOpenCheckpoint,
    onAcknowledgeHandoff,
    onGoLogs,
    onGoStart,
    onGoPipeline,
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
        primaryLabel: "Open checkpoint",
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
        statusLine: `Step done — review outputs from ${handoffStage.title}.`,
        primaryLabel: "Acknowledge & continue",
        primaryDisabled: false,
        secondaryLabel: "Review outputs",
        onPrimary: onAcknowledgeHandoff,
        onSecondary: () => onOpenCheckpoint(handoffStage.id),
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
        primaryLabel: "Open Pipeline",
        primaryDisabled: false,
        secondaryLabel: "View logs",
        onPrimary: onGoPipeline,
        onSecondary: onGoLogs,
        handoffStage: null,
      };
    }

    if (hint?.action === "checkpoint") {
      return {
        kind: "ready",
        statusLine: nextAction,
        primaryLabel: hint.label,
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
        primaryLabel: hint.label,
        primaryDisabled: jobRunning,
        secondaryLabel: "Open checkpoint",
        onPrimary: () => onExecute(body),
        onSecondary: () => onOpenCheckpoint(),
        handoffStage: null,
      };
    }

    if (nextAction) {
      return {
        kind: "ready",
        statusLine: nextAction,
        primaryLabel: "Open Pipeline",
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
    onExecute,
    onOpenCheckpoint,
    onAcknowledgeHandoff,
    onGoLogs,
    onGoStart,
    onGoPipeline,
  ]);
}
