import type { RunData, StageInfo } from "../types";
import { getHandoffPathsLocal } from "./checkpoint";
import { resolveJobStatusContext } from "./operatorStatus";
import { parseFileCountFromMessage } from "./pendingAction";
import type { PipelineNavState } from "./pipelineNavigation";
import { firstTodoItem, guidanceHasTodo } from "./stageGuidance";
import { checkpointPrimaryLabel } from "./checkpointLabels";

export type StagePrimaryActionKind =
  | "run"
  | "checkpoint"
  | "handoff"
  | "navigate"
  | "waiting"
  | "none";

export interface StagePrimaryActionSpec {
  kind: StagePrimaryActionKind;
  label: string;
  sublabel?: string;
  disabled: boolean;
  running?: boolean;
  /** Stage to select before acting (navigate / checkpoint). */
  targetStageId?: string;
  /** When kind is run, explicit stage to execute (defaults to next runnable). */
  runStageId?: string;
}

export function resolveStagePrimaryAction(
  stage: StageInfo,
  run: RunData,
  nav: PipelineNavState,
  opts: {
    jobRunning: boolean;
    hasPrecleanOffer: boolean;
  },
): StagePrimaryActionSpec | null {
  const job = run.job;
  const jobCtx = resolveJobStatusContext(run, opts.jobRunning);
  const runningStageId = job?.current_stage || job?.stage;
  const isRunningThisStage =
    jobCtx.isRunning && runningStageId === stage.id;

  if (jobCtx.isRunning) {
    if (isRunningThisStage) {
      return {
        kind: "waiting",
        label: `Running ${stage.title}…`,
        sublabel: job?.message || "Watch the activity log for progress.",
        disabled: true,
        running: true,
      };
    }
    return {
      kind: "waiting",
      label: "Another step is running",
      sublabel: "Wait for it to finish before starting a new action.",
      disabled: true,
    };
  }

  const handoffPaths = getHandoffPathsLocal(stage, run.log_tail);
  const needsHandoff =
    stage.status === "done" &&
    handoffPaths.length > 0 &&
    !run.handoff_ack?.[stage.id];

  if (
    jobCtx.awaitingWriteApproval &&
    (job?.pending_write_stage === stage.id ||
      job?.stage === stage.id ||
      stage.status === "awaiting_write_approval")
  ) {
    const fileCount = parseFileCountFromMessage(job?.message);
    return {
      kind: "checkpoint",
      label: fileCount
        ? `Save ${fileCount} file${fileCount === 1 ? "" : "s"} & continue`
        : "Save & continue",
      sublabel: "Preview staged outputs if needed, then save to disk to advance.",
      disabled: false,
      targetStageId: stage.id,
    };
  }

  if (jobCtx.needsStageReuse && job?.stage === stage.id) {
    return {
      kind: "checkpoint",
      label: "Reuse or run fresh",
      sublabel: "Pick a prior execution with the same source audio, or regenerate.",
      disabled: false,
      targetStageId: stage.id,
    };
  }

  if (needsHandoff) {
    return {
      kind: "handoff",
      label: checkpointPrimaryLabel(stage.id, "handoff"),
      sublabel: "Review AI outputs above, then acknowledge to continue.",
      disabled: false,
      targetStageId: stage.id,
    };
  }

  if (
    stage.status === "action_required" ||
    (jobCtx.needsGate && job?.stage === stage.id)
  ) {
    return {
      kind: "checkpoint",
      label: checkpointPrimaryLabel(stage.id, "gate"),
      sublabel: "Complete the required operator steps for this stage.",
      disabled: false,
      targetStageId: stage.id,
    };
  }

  if (opts.hasPrecleanOffer && nav.precleanOffer) {
    return {
      kind: "waiting",
      label: "Choose an option below",
      sublabel: "Skip cleaning to keep original audio, or run MMAudio isolation.",
      disabled: true,
    };
  }

  if (stage.status === "locked") {
    const blocker = firstTodoItem(stage.guidance);
    return {
      kind: "waiting",
      label: "Locked — complete prerequisites first",
      sublabel: blocker?.label || "Finish earlier pipeline steps to unlock this one.",
      disabled: true,
    };
  }

  const prereqsMet = !(stage.guidance?.prerequisites || []).some((i) => i.status === "todo");
  const isNextRunnable = nav.nextStage?.id === stage.id && stage.status === "pending";

  if (isNextRunnable) {
    if (!prereqsMet) {
      const blocker = firstTodoItem(stage.guidance);
      return {
        kind: "waiting",
        label: "Complete prerequisites first",
        sublabel: blocker?.label || "Resolve the items listed below before running.",
        disabled: true,
      };
    }
    return {
      kind: "run",
      label: `Run ${stage.title}`,
      sublabel: nav.nextLine || "Starts this step and writes outputs to disk.",
      disabled: false,
      runStageId: stage.id,
    };
  }

  if (stage.status === "done") {
    if (nav.nextStage) {
      return {
        kind: "run",
        label: `Run ${nav.nextStage.title}`,
        sublabel: `Step ${nav.nextNumber ?? "?"} is up next in the pipeline.`,
        disabled: false,
        runStageId: nav.nextStage.id,
        targetStageId: nav.nextStage.id,
      };
    }
    if (!guidanceHasTodo(stage.guidance)) {
      return {
        kind: "none",
        label: "Step complete",
        sublabel: "No further action needed on this stage.",
        disabled: true,
      };
    }
    return null;
  }

  if (nav.nextStage && nav.nextStage.id !== stage.id) {
    return {
      kind: "navigate",
      label: `Go to step ${nav.nextNumber ?? "?"} — ${nav.nextStage.title}`,
      sublabel: "That step is next in the pipeline.",
      disabled: false,
      targetStageId: nav.nextStage.id,
    };
  }

  if (stage.status === "pending" && !prereqsMet) {
    const blocker = firstTodoItem(stage.guidance);
    return {
      kind: "waiting",
      label: "Complete prerequisites first",
      sublabel: blocker?.label,
      disabled: true,
    };
  }

  return null;
}
