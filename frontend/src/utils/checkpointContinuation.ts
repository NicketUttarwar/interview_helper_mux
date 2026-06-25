import type { JobState, RunData } from "../types";
import { findPendingFocusStage } from "./checkpoint";
import { findNextRunnableStage } from "./preclean";
import { pendingWriteInfo, stageAwaitingWriteApproval } from "./writeApproval";
import { resolveOperatorAction } from "./resolveOperatorAction";
import { isJobActivelyRunning } from "./jobStatus";
import type { ExecuteBody } from "../types";

export interface WriteApprovalAdvanceOpts {
  savedStageId: string;
  nextStageId?: string | null;
  job?: JobState | null;
}

/** Optimistic run patch so the GUI leaves write-approval before the next refresh. */
export function patchRunAfterWriteApproval(
  run: RunData,
  opts: WriteApprovalAdvanceOpts,
): RunData {
  const { savedStageId, nextStageId, job } = opts;
  const meta = run.meta ? { ...run.meta } : {};
  const pendingRaw = meta.pending_write_approval;
  if (pendingRaw && typeof pendingRaw === "object") {
    const pending = { ...(pendingRaw as Record<string, unknown>) };
    delete pending[savedStageId];
    if (Object.keys(pending).length) {
      meta.pending_write_approval = pending;
    } else {
      delete meta.pending_write_approval;
    }
  }

  const stages = run.stages.map((s) =>
    s.id === savedStageId ? { ...s, status: "done" as const } : s,
  );

  const clearWriteFields = {
    pending_write_stage: undefined,
    pending_write_paths: undefined,
    awaiting_write_approval: false,
  };

  let nextJob: JobState;
  const jobIndicatesRunning =
    job && typeof job === "object" && isJobActivelyRunning(job as JobState);
  if (jobIndicatesRunning) {
    nextJob = { ...(job as JobState), ...clearWriteFields };
  } else if (nextStageId) {
    nextJob = {
      status: "running",
      stage: nextStageId,
      current_stage: nextStageId,
      message: `Running ${nextStageId.replace(/_/g, " ")}…`,
      ...clearWriteFields,
    };
  } else {
    nextJob = {
      status: "complete",
      stage: savedStageId,
      current_stage: undefined,
      message: "Step complete — continuing pipeline.",
      ...clearWriteFields,
    };
  }

  const reuseStage = job?.needs_stage_reuse ? job.stage || nextStageId : null;
  const reuseBlocking =
    reuseStage && job
      ? {
          blocked: true as const,
          reason: "stage_reuse" as const,
          stage_id: reuseStage,
          message: job.message,
        }
      : undefined;

  const clearWriteBlocking = (blocking: RunData["blocking"]) => {
    if (!blocking || blocking.reason !== "write_approval") return blocking;
    return undefined;
  };

  return {
    ...run,
    meta,
    stages,
    job: nextJob,
    blocking: reuseBlocking ?? clearWriteBlocking(run.blocking),
    journey: run.journey
      ? {
          ...run.journey,
          blocking: reuseBlocking ?? clearWriteBlocking(run.journey.blocking),
          active_substep_id: reuseStage
            ? `stage_reuse:${reuseStage}`
            : nextStageId && isJobActivelyRunning(nextJob)
              ? `run:${nextStageId}`
              : run.journey.active_substep_id,
        }
      : run.journey,
  };
}

export type ExecuteJobSource = "user" | "checkpoint_continue";

export interface AdvancePipelineOpts {
  run: RunData | null;
  runId: string | null;
  apiGrants: Record<string, boolean>;
  selectedStageId: string | null;
  executeJob: (body: ExecuteBody, opts?: { source?: ExecuteJobSource }) => Promise<void>;
  selectStage: (id: string) => Promise<void>;
  expandStage: (id: string) => void;
  setActiveSubstepId: (id: string | null) => void;
  setPipelineSubTab: (tab: "stage" | "files" | "logs") => void;
  showToast: (msg: string, level?: "info" | "success" | "warning" | "error") => void;
  refreshRun: () => Promise<RunData | null>;
  navigateToNextBlocker: () => Promise<void>;
}

export interface ReconcileBusyOpts {
  runId: string;
  syncJobRunning: (id: string) => Promise<JobState | null>;
  refreshRun: () => Promise<RunData | null>;
  startJobPoll: () => void;
  setActivityLogTab: (tab: "live" | "all" | "step") => void;
  showToast: (msg: string, level?: "info" | "success" | "warning" | "error") => void;
  context?: "save" | "execute" | "generic";
}

/** After checkpoint API success: run next stage or focus next blocker. */
export async function advancePipeline(opts: AdvancePipelineOpts): Promise<boolean> {
  const refreshed = opts.runId ? await opts.refreshRun() : opts.run;
  if (!refreshed) return false;

  const write = pendingWriteInfo(refreshed);
  if (write?.paths.length) {
    await opts.selectStage(write.stageId);
    opts.setPipelineSubTab("files");
    opts.expandStage(write.stageId);
    return false;
  }

  const blocking = refreshed.journey?.blocking ?? refreshed.blocking;
  if (blocking?.blocked && blocking.stage_id) {
    await opts.selectStage(blocking.stage_id);
    opts.expandStage(blocking.stage_id);
    if (blocking.reason === "stage_reuse") {
      opts.setActiveSubstepId(`stage_reuse:${blocking.stage_id}`);
      opts.setPipelineSubTab("stage");
      return false;
    }
    if (blocking.reason === "handoff_review") {
      opts.setActiveSubstepId(`handoff:${blocking.stage_id}`);
      opts.setPipelineSubTab("stage");
      return false;
    }
    if (blocking.reason === "write_approval") {
      opts.setPipelineSubTab("files");
      return false;
    }
    opts.setPipelineSubTab("stage");
    return false;
  }

  const focusId = findPendingFocusStage(refreshed, opts.apiGrants);
  if (focusId) {
    await opts.selectStage(focusId);
    opts.expandStage(focusId);
  }

  const nextAction = resolveOperatorAction(refreshed, {
    selectedStageId: opts.selectedStageId,
    jobRunning: false,
    apiGrants: opts.apiGrants,
  });

  if (nextAction.mode === "needs_you" && nextAction.stageId) {
    await opts.selectStage(nextAction.stageId);
    opts.expandStage(nextAction.stageId);
    if (nextAction.substepId) opts.setActiveSubstepId(nextAction.substepId);
    return false;
  }

  if (
    nextAction.mode === "idle" &&
    nextAction.stageId &&
    nextAction.primaryKind === "run_stage"
  ) {
    const nextStage = refreshed.stages.find((s) => s.id === nextAction.stageId);
    if (nextStage) {
      opts.showToast(`Starting ${nextStage.title}…`);
      await opts.selectStage(nextStage.id);
      opts.expandStage(nextStage.id);
      await opts.executeJob(
        { mode: "stage", stage: nextStage.id },
        { source: "checkpoint_continue" },
      );
      return true;
    }
  }

  const next = findNextRunnableStage(refreshed.stages, refreshed.meta);
  if (next) {
    opts.showToast(`Starting ${next.title}…`);
    await opts.selectStage(next.id);
    opts.expandStage(next.id);
    await opts.executeJob(
      { mode: "stage", stage: next.id },
      { source: "checkpoint_continue" },
    );
    return true;
  }

  await opts.navigateToNextBlocker();
  return false;
}

/** HTTP 409 / run busy — reconcile client with server job state. */
export async function reconcileBusyRun(opts: ReconcileBusyOpts): Promise<{
  jobRunning: boolean;
  writeApprovalCleared: boolean;
}> {
  const job = await opts.syncJobRunning(opts.runId);
  const running = isJobActivelyRunning(job);
  if (running) {
    const stage = job?.current_stage || job?.stage;
    const saving = job?.mode === "write_approval";
    const isIngest =
      stage === "ingest" || (job?.message || "").toLowerCase().includes("hash");
    const msg = opts.context === "save"
      ? saving
        ? "Save in progress — watch Activity (Live)."
        : isIngest
          ? "Ingest running — watch Activity (Live)."
          : "Step running — watch Activity (Live)."
      : "A step is already running — watch Activity (Live).";
    opts.showToast(msg, "warning");
    opts.setActivityLogTab("live");
    opts.startJobPoll();
    return { jobRunning: true, writeApprovalCleared: false };
  }

  const refreshed = await opts.refreshRun();
  const sid = refreshed?.job?.pending_write_stage || refreshed?.job?.stage;
  const cleared =
    !refreshed?.job?.awaiting_write_approval &&
    refreshed?.job?.status !== "awaiting_write_approval" &&
    (!sid || !stageAwaitingWriteApproval(refreshed, sid));
  return { jobRunning: false, writeApprovalCleared: cleared };
}
