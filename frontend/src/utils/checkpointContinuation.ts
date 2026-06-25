import type { JobState, PipelineSubTab, RunData } from "../types";
import { findPendingFocusStage } from "./checkpoint";
import { findNextRunnableStage } from "./preclean";
import { readyForStageMessage } from "./stageAdvance";
import { pendingWriteInfo, stageAwaitingWriteApproval } from "./writeApproval";
import { resolveOperatorAction } from "./resolveOperatorAction";
import { isJobActivelyRunning } from "./jobStatus";
import { resolveFocusStepId } from "./resolveActiveStep";
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
      meta.pending_write_approval = pending as RunData["meta"] extends { pending_write_approval?: infer P } ? P : never;
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
      status: "complete",
      stage: savedStageId,
      current_stage: undefined,
      message: `Step complete — ready for ${nextStageId.replace(/_/g, " ")}.`,
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
            : nextStageId
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
  selectStage: (id: string, opts?: { stepId?: string | null }) => Promise<void>;
  expandStage: (id: string) => void;
  setActiveSubstepId: (id: string | null) => void;
  setActiveStepId?: (id: string | null) => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  showToast: (msg: string, level?: "info" | "success" | "warning" | "error") => void;
  refreshRun: () => Promise<RunData | null>;
  navigateToNextBlocker: () => Promise<void>;
}

export interface FocusStageWorkbenchOpts {
  run: RunData | null;
  stageId: string;
  selectStage: (id: string, opts?: { stepId?: string | null }) => Promise<void>;
  expandStage: (id: string) => void;
  setActiveStepId?: (id: string | null) => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  substepId?: string | null;
  blockingReason?: string | null;
  subTab?: PipelineSubTab;
}

/** Select a stage and land on the correct numbered workbench step. */
export async function focusStageWorkbench(opts: FocusStageWorkbenchOpts): Promise<string | null> {
  const stepId = resolveFocusStepId(opts.run, opts.stageId, {
    substepId: opts.substepId,
    blockingReason: opts.blockingReason,
  });
  await opts.selectStage(opts.stageId, { stepId });
  opts.expandStage(opts.stageId);
  opts.setPipelineSubTab(opts.subTab ?? "stage");
  if (stepId) opts.setActiveStepId?.(stepId);
  return stepId;
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
    await focusStageWorkbench({
      run: refreshed,
      stageId: write.stageId,
      selectStage: opts.selectStage,
      expandStage: opts.expandStage,
      setActiveStepId: opts.setActiveStepId,
      setPipelineSubTab: opts.setPipelineSubTab,
      blockingReason: "write_approval",
    });
    return false;
  }

  const blocking = refreshed.journey?.blocking ?? refreshed.blocking;
  if (blocking?.blocked && blocking.stage_id) {
    const substepId =
      blocking.reason === "stage_reuse"
        ? `stage_reuse:${blocking.stage_id}`
        : blocking.reason === "handoff_review"
          ? `handoff:${blocking.stage_id}`
          : blocking.reason === "write_approval"
            ? `write_approval:${blocking.stage_id}`
            : null;
    if (substepId) opts.setActiveSubstepId(substepId);
    await focusStageWorkbench({
      run: refreshed,
      stageId: blocking.stage_id,
      selectStage: opts.selectStage,
      expandStage: opts.expandStage,
      setActiveStepId: opts.setActiveStepId,
      setPipelineSubTab: opts.setPipelineSubTab,
      substepId,
      blockingReason: blocking.reason,
    });
    return false;
  }

  const focusId = findPendingFocusStage(refreshed, opts.apiGrants);
  if (focusId) {
    await focusStageWorkbench({
      run: refreshed,
      stageId: focusId,
      selectStage: opts.selectStage,
      expandStage: opts.expandStage,
      setActiveStepId: opts.setActiveStepId,
      setPipelineSubTab: opts.setPipelineSubTab,
    });
  }

  const nextAction = resolveOperatorAction(refreshed, {
    selectedStageId: opts.selectedStageId,
    jobRunning: false,
    apiGrants: opts.apiGrants,
  });

  if (nextAction.mode === "needs_you" && nextAction.stageId) {
    if (nextAction.substepId) opts.setActiveSubstepId(nextAction.substepId);
    await focusStageWorkbench({
      run: refreshed,
      stageId: nextAction.stageId,
      selectStage: opts.selectStage,
      expandStage: opts.expandStage,
      setActiveStepId: opts.setActiveStepId,
      setPipelineSubTab: opts.setPipelineSubTab,
      substepId: nextAction.substepId,
    });
    return false;
  }

  if (
    nextAction.mode === "idle" &&
    nextAction.stageId &&
    nextAction.primaryKind === "run_stage"
  ) {
    const nextStage = refreshed.stages.find((s) => s.id === nextAction.stageId);
    if (nextStage) {
      opts.showToast(readyForStageMessage(nextStage.title), "info");
      await focusStageWorkbench({
        run: refreshed,
        stageId: nextStage.id,
        selectStage: opts.selectStage,
        expandStage: opts.expandStage,
        setActiveStepId: opts.setActiveStepId,
        setPipelineSubTab: opts.setPipelineSubTab,
        substepId: "run",
      });
      return false;
    }
  }

  const next = findNextRunnableStage(refreshed.stages, refreshed.meta);
  if (next) {
    opts.showToast(readyForStageMessage(next.title), "info");
    await focusStageWorkbench({
      run: refreshed,
      stageId: next.id,
      selectStage: opts.selectStage,
      expandStage: opts.expandStage,
      setActiveStepId: opts.setActiveStepId,
      setPipelineSubTab: opts.setPipelineSubTab,
      substepId: "run",
    });
    return false;
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
