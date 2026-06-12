import { useMemo } from "react";
import type { LiveStatus, LogEntry, RunData } from "../types";
import { PHASE_LABELS } from "../constants/phases";
import { stageTitleForId } from "../utils/checkpoint";
import { isJobActivelyRunning } from "../utils/jobStatus";
import { buildNumberedStages, resolvePipelineNav } from "../utils/pipelineNavigation";
import { useOperatorCommand } from "./useOperatorCommand";
import {
  WORKFLOW_STEPS,
  currentWorkflowStep,
  workflowStepIndex,
} from "../utils/workflowSteps";

export function useLiveStatus(
  run: RunData | null,
  opts: {
    jobRunning: boolean;
    selectedStageId: string | null;
    logEntries: LogEntry[];
    apiGrants: Record<string, boolean>;
    onExecute: Parameters<typeof useOperatorCommand>[1]["onExecute"];
    onOpenCheckpoint: Parameters<typeof useOperatorCommand>[1]["onOpenCheckpoint"];
    onAcknowledgeHandoff: Parameters<typeof useOperatorCommand>[1]["onAcknowledgeHandoff"];
    onGoLogs: () => void;
    onGoStart: () => void;
    onGoPipeline: () => void;
  },
): LiveStatus {
  const cmd = useOperatorCommand(run, {
    jobRunning: opts.jobRunning,
    onExecute: opts.onExecute,
    onOpenCheckpoint: opts.onOpenCheckpoint,
    onAcknowledgeHandoff: opts.onAcknowledgeHandoff,
    onGoLogs: opts.onGoLogs,
    onGoStart: opts.onGoStart,
    onGoPipeline: opts.onGoPipeline,
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

    let activityKind = cmd.kind as LiveStatus["activityKind"];
    let headline = cmd.statusLine;
    let subline = run.journey?.next_action || nav.statusLine || "";

    if (job?.status === "interrupted") {
      activityKind = "interrupted";
      headline = "Run interrupted";
      subline = job.message || "Server restarted during a job — re-run the last step.";
    } else if (opts.jobRunning || isJobActivelyRunning(job)) {
      activityKind = "running";
      const stageTitle =
        stageTitleForId(run.stages, runningStageId) ||
        runningStageId?.replace(/_/g, " ") ||
        "pipeline";
      if (jobProgress) {
        headline = `Running step ${jobProgress.index}/${jobProgress.total} — ${stageTitle}`;
      } else {
        headline = `Running — ${stageTitle}`;
      }
      subline = job?.message || subline;
    } else if (job?.status === "complete") {
      headline = "Step finished";
      subline = job.message || subline;
    } else if (job?.status === "error") {
      activityKind = "error";
      headline = "Step failed";
      subline = job.last_error?.message || job.message || "See activity log for details.";
    } else if (pipelineStep?.number) {
      headline = `Step ${pipelineStep.number}/${pipelineStep.total} — ${pipelineStep.title}`;
    }

    return {
      activityKind,
      headline,
      subline,
      pipelineStep,
      workflowPhase,
      runningStageId,
      focusStageId,
      primaryLabel: cmd.primaryLabel,
      primaryDisabled: cmd.primaryDisabled,
      secondaryLabel: cmd.secondaryLabel,
      onPrimary: cmd.onPrimary,
      onSecondary: cmd.onSecondary,
      errorCount,
      jobProgress,
      lastError: job?.last_error ?? null,
    };
  }, [run, opts, cmd]);
}
