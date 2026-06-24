import { useMemo } from "react";
import type { AppTab, LiveStatus, LogEntry, RunData } from "../types";
import { PHASE_LABELS } from "../constants/phases";
import { resolveOperatorAction } from "../utils/resolveOperatorAction";
import { buildNumberedStages, resolvePipelineNav } from "../utils/pipelineNavigation";
import { isJobActivelyRunning } from "../utils/jobStatus";
import { useOperatorCommand, type OperatorCommandState } from "./useOperatorCommand";
import {
  WORKFLOW_STEPS,
  currentWorkflowStep,
  workflowStepIndex,
} from "../utils/workflowSteps";

export interface LiveStatusCopyInput {
  run: RunData;
  jobRunning: boolean;
  selectedStageId: string | null;
  logEntries: LogEntry[];
  apiGrants: Record<string, boolean>;
  jobCompleteAt?: number | null;
  cmd: Pick<OperatorCommandState, "kind" | "statusLine" | "primaryLabel" | "onPrimary">;
}

/** Pure headline/subline derivation for LiveStatusBar (testable without React). */
export function deriveLiveStatusCopy(input: LiveStatusCopyInput): {
  activityKind: LiveStatus["activityKind"];
  headline: string;
  subline: string;
  primaryLabel: string | null;
  onPrimary: (() => void) | null;
} {
  const { run, cmd } = input;
  const action = resolveOperatorAction(run, {
    selectedStageId: input.selectedStageId,
    jobRunning: input.jobRunning,
    apiGrants: input.apiGrants,
  });

  const recentComplete =
    input.jobCompleteAt != null && Date.now() - input.jobCompleteAt < 30_000;
  const job = run.job;

  let activityKind = cmd.kind as LiveStatus["activityKind"];
  let headline = action.headline || cmd.statusLine;
  let subline = action.subline || run.journey?.next_action || "";
  let primaryLabel = action.primaryDisabled ? null : action.primaryLabel;
  let onPrimary: (() => void) | null = cmd.onPrimary;

  const runningStage = job?.current_stage || job?.stage;
  const jobMsg = (job?.message || "").toLowerCase();
  if (
    input.jobRunning &&
    (runningStage === "ingest" || jobMsg.includes("hash") || jobMsg.includes("ingest"))
  ) {
    subline =
      job?.message ||
      "Hashing audio — this can take a few minutes for long files. Watch Activity log.";
  }

  if (job?.status === "interrupted") {
    activityKind = "interrupted";
    headline = "Run interrupted";
    subline = job.message || "Server restarted during a job — re-run the last step.";
  } else if (input.jobRunning || job?.status === "running" || job?.status === "running_with_warnings") {
    activityKind = "running";
    headline = action.headline;
    subline = job?.message || action.subline || subline;
    primaryLabel = "View logs";
    onPrimary = cmd.onPrimary;
  } else if (job?.status === "complete" || recentComplete) {
    headline = "Step finished";
    subline = action.subline || job?.message || subline;
  } else if (job?.status === "error" || action.mode === "error") {
    activityKind = "error";
    headline = action.headline || "Step failed";
    subline = job?.last_error?.message || job?.message || action.subline || subline;
    primaryLabel = action.primaryDisabled ? null : action.primaryLabel;
    onPrimary = cmd.onPrimary;
  } else if (action.mode === "needs_you") {
    activityKind = "blocked";
    primaryLabel = action.primaryLabel;
  }

  return { activityKind, headline, subline, primaryLabel, onPrimary };
}

export function useLiveStatus(
  run: RunData | null,
  opts: {
    jobRunning: boolean;
    actionBusy?: boolean;
    selectedStageId: string | null;
    logEntries: LogEntry[];
    apiGrants: Record<string, boolean>;
    activeTab?: AppTab;
    jobCompleteAt?: number | null;
    onExecute: Parameters<typeof useOperatorCommand>[1]["onExecute"];
    onRunNext: () => void;
    onOpenCheckpoint: Parameters<typeof useOperatorCommand>[1]["onOpenCheckpoint"];
    onAcknowledgeHandoff: Parameters<typeof useOperatorCommand>[1]["onAcknowledgeHandoff"];
    onApproveWrite?: (stageId: string) => void;
    onGoLogs: () => void;
    onGoStart: () => void;
    onGoPipeline: () => void;
    onGoStory?: () => void;
    onGoProfile?: () => void;
    onScrollPreview?: () => void;
    showToast?: (msg: string, level?: "info" | "success" | "warning" | "error") => void;
  },
): LiveStatus {
  const cmd = useOperatorCommand(run, {
    jobRunning: opts.jobRunning,
    actionBusy: opts.actionBusy,
    selectedStageId: opts.selectedStageId,
    apiGrants: opts.apiGrants,
    surface: "header",
    activeTab: opts.activeTab,
    onExecute: opts.onExecute,
    onRunNext: opts.onRunNext,
    onOpenCheckpoint: opts.onOpenCheckpoint,
    onAcknowledgeHandoff: opts.onAcknowledgeHandoff,
    onApproveWrite: opts.onApproveWrite,
    onGoLogs: opts.onGoLogs,
    onGoStart: opts.onGoStart,
    onGoPipeline: opts.onGoPipeline,
    onGoStory: opts.onGoStory,
    onGoProfile: opts.onGoProfile,
    onScrollPreview: opts.onScrollPreview,
    showToast: opts.showToast,
  });

  return useMemo(() => {
    const errorCount = opts.logEntries.filter((e) => e.level === "error").length;
    const stepId = currentWorkflowStep(run);
    const phaseIndex = workflowStepIndex(stepId);
    const phaseDef = WORKFLOW_STEPS[phaseIndex];
    const workflowPhase = {
      index: phaseIndex,
      total: WORKFLOW_STEPS.length,
      id: stepId,
      label: phaseDef?.label ?? "Start",
    };

    const empty: LiveStatus = {
      activityKind: "no_run",
      headline: "No active run",
      subline: "Pick source audio on Start or resume an execution.",
      pipelineStep: null,
      workflowPhase,
      runningStageId: null,
      focusStageId: null,
      primaryLabel: cmd.primaryLabel,
      primaryDisabled: cmd.primaryDisabled,
      secondaryLabel: cmd.secondaryLabel,
      onPrimary: cmd.onPrimary,
      onSecondary: cmd.onSecondary,
      errorCount,
      jobProgress: null,
      lastError: null,
    };

    if (!run) return { ...empty, activityKind: "no_run" };

    const nav = resolvePipelineNav(run, {
      selectedStageId: opts.selectedStageId,
      jobRunning: opts.jobRunning,
      apiGrants: opts.apiGrants,
    });
    const numbered = buildNumberedStages(run.stages);
    const job = run.job;
    const runningStageId =
      opts.jobRunning || isJobActivelyRunning(job)
        ? job?.current_stage || job?.stage || null
        : null;
    const focusStageId = nav.focusStageId;
    const currentNum = nav.currentNumber;
    const currentStage = nav.currentStage;
    const pipelineStep = currentStage
      ? {
          number: currentNum,
          total: numbered.length,
          title: currentStage.title,
          phaseLabel:
            currentStage.guidance?.phase_label ||
            PHASE_LABELS[currentStage.operator_phase ?? ""] ||
            "Step",
        }
      : null;

    const jobProgress =
      job?.stage_index && job?.stage_total
        ? { index: job.stage_index, total: job.stage_total }
        : null;

    const derived = deriveLiveStatusCopy({
      run,
      jobRunning: opts.jobRunning,
      selectedStageId: opts.selectedStageId,
      logEntries: opts.logEntries,
      apiGrants: opts.apiGrants,
      jobCompleteAt: opts.jobCompleteAt,
      cmd,
    });

    return {
      activityKind: derived.activityKind,
      headline: derived.headline,
      subline: derived.subline,
      pipelineStep,
      workflowPhase,
      runningStageId,
      focusStageId,
      primaryLabel: derived.primaryLabel,
      primaryDisabled: cmd.primaryDisabled,
      secondaryLabel: cmd.secondaryLabel,
      onPrimary: derived.onPrimary,
      onSecondary: cmd.onSecondary,
      errorCount,
      jobProgress,
      lastError: job?.last_error ?? null,
    };
  }, [run, opts, cmd]);
}
