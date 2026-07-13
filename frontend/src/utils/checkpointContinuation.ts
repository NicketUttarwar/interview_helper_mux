import type { JobState, PipelineSubTab, RunData, AppConfig } from "../types";
import { findPendingFocusStage, resolveOperatorFocusStageId } from "./checkpoint";
import { findNextRunnableStage } from "./preclean";
import { firstUpstreamBlocker } from "./stageOutputs";
import { readyForStageMessage } from "./stageAdvance";
import { pendingWriteInfo, stageAwaitingWriteApproval } from "./writeApproval";
import { resolveOperatorAction } from "./resolveOperatorAction";
import { isJobActivelyRunning } from "./jobStatus";
import { resolveFocusStepId } from "./resolveActiveStep";
import type { ExecuteBody } from "../types";
import { executeBodyForStage } from "./operatorActionHandlers";
import { stageNeedsAttention, topAttentionItem } from "./attentionQueue";
import {
  autopilotBlocksAutoRun,
  canAutoRunStage,
  isPipelineAutopilotEnabled,
  isPipelineComplete,
  shouldAutoNavigateFromStage,
} from "./pipelineAutopilot";
import {
  canAttemptAutopilotCheckpoint,
  clearAutopilotCheckpointAttempts,
  recordAutopilotCheckpointAttempt,
  resolveAutopilotCheckpoint,
} from "./autopilotResolution";
import {
  isAutoNavConsumed,
  markAutoNavConsumed,
  type AutoNavTarget,
} from "./autoNavigationLedger";

/** Who triggered navigation — auto_surface is once per stage/step per server session. */
export type NavigationIntent = "auto_surface" | "user_continue";

/** Auto fix-all when autopilot is enabled. Returns true if an action ran. */
export async function tryAutopilotCheckpointResolution(
  opts: AdvancePipelineOpts,
): Promise<boolean> {
  if (!isPipelineAutopilotEnabled(opts.config) || !opts.runId) return false;

  const run = opts.runId ? await opts.refreshRun() : opts.run;
  if (!run) return false;

  const checkpoint = resolveAutopilotCheckpoint(run, opts.config);
  if (!checkpoint) return false;
  if (!canAttemptAutopilotCheckpoint(opts.runId, checkpoint)) return false;

  recordAutopilotCheckpointAttempt(opts.runId, checkpoint);

  if (checkpoint.kind === "write_approval") {
    return false;
  }

  if (!opts.fixAllAndContinueStage) return false;
  opts.showToast("Autopilot: fixing artifact issues…", "info");
  const ok = await opts.fixAllAndContinueStage(checkpoint.stageId);
  if (ok) {
    clearAutopilotCheckpointAttempts(opts.runId, checkpoint.stageId);
    return true;
  }
  return false;
}

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
  selectStage: (id: string, opts?: { stepId?: string | null; pinned?: boolean }) => Promise<void>;
  expandStage: (id: string) => void;
  setActiveSubstepId: (id: string | null) => void;
  setActiveStepId?: (id: string | null) => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  showToast: (msg: string, level?: "info" | "success" | "warning" | "error") => void;
  refreshRun: () => Promise<RunData | null>;
  navigateToNextBlocker: () => Promise<void>;
  /** When true, automatically start the next automated stage after focusing it. */
  autoRun?: boolean;
  config?: AppConfig | null;
  /** Auto-acknowledge AI handoff checkpoints when autopilot is active. */
  acknowledgeHandoff?: () => Promise<void>;
  /** Autopilot: auto-resolve ITR issues (Fix all & continue). */
  fixAllAndContinueStage?: (stageId: string) => Promise<boolean>;
  /** Autopilot: auto-save staged outputs. */
  approveWriteAndContinue?: (stageId?: string) => Promise<boolean>;
  /** auto_surface = show operator focus once per stage/step; user_continue = always navigate. */
  navigationIntent?: NavigationIntent;
}

export interface FocusStageWorkbenchOpts {
  run: RunData | null;
  stageId: string;
  selectStage: (id: string, opts?: { stepId?: string | null; pinned?: boolean }) => Promise<void>;
  expandStage: (id: string) => void;
  setActiveStepId?: (id: string | null) => void;
  setPipelineSubTab: (tab: PipelineSubTab) => void;
  substepId?: string | null;
  blockingReason?: string | null;
  subTab?: PipelineSubTab;
  navigationIntent?: NavigationIntent;
}

function resolveFocusTarget(
  run: RunData | null,
  stageId: string,
  opts: Pick<FocusStageWorkbenchOpts, "substepId" | "blockingReason">,
): AutoNavTarget {
  const stepId = resolveFocusStepId(run, stageId, {
    substepId: opts.substepId,
    blockingReason: opts.blockingReason,
  });
  return { stageId, stepId };
}

function shouldSkipAutoSurfaceNavigation(
  intent: NavigationIntent | undefined,
  target: AutoNavTarget,
): boolean {
  if (intent !== "auto_surface") return false;
  return isAutoNavConsumed(target);
}

/** Select a stage and land on the correct numbered workbench step. */
export async function focusStageWorkbench(opts: FocusStageWorkbenchOpts): Promise<string | null> {
  const intent = opts.navigationIntent ?? "user_continue";
  const target = resolveFocusTarget(opts.run, opts.stageId, opts);
  if (shouldSkipAutoSurfaceNavigation(intent, target)) {
    return null;
  }

  const stepId = target.stepId ?? null;
  await opts.selectStage(opts.stageId, { stepId });
  opts.expandStage(opts.stageId);
  opts.setPipelineSubTab(opts.subTab ?? "stage");
  if (stepId) opts.setActiveStepId?.(stepId);

  if (intent === "auto_surface") {
    markAutoNavConsumed(target);
  }
  return stepId;
}

function resolveFocusSubstepId(run: RunData, stageId: string): string | null {
  const blocking = run.journey?.blocking ?? run.blocking;
  if (blocking?.stage_id === stageId) {
    if (blocking.reason === "stage_reuse") return `stage_reuse:${stageId}`;
    if (blocking.reason === "handoff_review") return `handoff:${stageId}`;
    if (blocking.reason === "write_approval") return `write_approval:${stageId}`;
    if (blocking.reason === "operator_decisions") return `operator_decisions:${stageId}`;
  }
  if (run.job?.needs_stage_reuse && run.job.stage === stageId) {
    return `stage_reuse:${stageId}`;
  }
  return null;
}

function shouldDeferFocusNavigation(
  run: RunData,
  currentId: string,
  focusId: string,
  grants: Record<string, boolean>,
): boolean {
  if (!currentId || currentId === focusId) return false;
  if (!stageNeedsAttention(run, currentId, grants)) return false;
  const top = topAttentionItem(run, grants);
  if (top?.stageId === focusId) return false;
  return true;
}

/** Keep sidebar + workbench aligned with the run's next operator focus (navigation only). */
export async function syncPipelineStageFocus(opts: AdvancePipelineOpts): Promise<boolean> {
  if (opts.config?.journey_ui?.enabled === false) return false;

  const refreshed = opts.runId ? await opts.refreshRun() : opts.run;
  if (!refreshed) return false;
  if (isPipelineComplete(refreshed)) return false;

  const focusId = resolveOperatorFocusStageId(refreshed, opts.apiGrants);
  if (!focusId) return false;

  const currentId = opts.selectedStageId;
  if (currentId && shouldDeferFocusNavigation(refreshed, currentId, focusId, opts.apiGrants)) {
    return false;
  }

  const substepId = resolveFocusSubstepId(refreshed, focusId);
  const blocking = refreshed.journey?.blocking ?? refreshed.blocking;
  const blockingReason =
    blocking?.stage_id === focusId ? blocking.reason ?? null : null;

  if (substepId) opts.setActiveSubstepId(substepId);

  const navIntent = opts.navigationIntent ?? "auto_surface";
  const target = resolveFocusTarget(refreshed, focusId, { substepId, blockingReason });
  if (shouldSkipAutoSurfaceNavigation(navIntent, target)) {
    return false;
  }

  const stepId = await focusStageWorkbench({
    run: refreshed,
    stageId: focusId,
    selectStage: (id, selOpts) =>
      opts.selectStage(id, { ...selOpts, pinned: false }),
    expandStage: opts.expandStage,
    setActiveStepId: opts.setActiveStepId,
    setPipelineSubTab: opts.setPipelineSubTab,
    substepId,
    blockingReason,
    navigationIntent: navIntent,
  });

  return Boolean(stepId) || focusId !== currentId;
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

  const navIntent = opts.navigationIntent ?? "user_continue";

  const autoRunEnabled =
    opts.autoRun === true && isPipelineAutopilotEnabled(opts.config);

  const tryStartStage = async (stageId: string): Promise<boolean> => {
    if (!autoRunEnabled || !canAutoRunStage(stageId, refreshed, opts.config)) return false;
    const blocker = firstUpstreamBlocker(refreshed.stages, stageId);
    if (blocker) {
      await focusStageWorkbench({
        run: refreshed,
        stageId: blocker.id,
        selectStage: opts.selectStage,
        expandStage: opts.expandStage,
        setActiveStepId: opts.setActiveStepId,
        setPipelineSubTab: opts.setPipelineSubTab,
        navigationIntent: navIntent,
      });
      return false;
    }
    await opts.executeJob(executeBodyForStage(stageId), { source: "checkpoint_continue" });
    return true;
  };

  if (isPipelineComplete(refreshed)) {
    return false;
  }

  if (autoRunEnabled) {
    const resolved = await tryAutopilotCheckpointResolution(opts);
    if (resolved) {
      const after = opts.runId ? await opts.refreshRun() : refreshed;
      if (after && !autopilotBlocksAutoRun(after, opts.config)) {
        return advancePipeline({ ...opts, run: after, autoRun: true });
      }
      return true;
    }
  }

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
      navigationIntent: navIntent,
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
            : blocking.reason === "operator_decisions"
              ? `operator_decisions:${blocking.stage_id}`
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
      navigationIntent: navIntent,
    });
    return false;
  }

  const focusId = resolveOperatorFocusStageId(refreshed, opts.apiGrants);
  if (focusId) {
    await focusStageWorkbench({
      run: refreshed,
      stageId: focusId,
      selectStage: opts.selectStage,
      expandStage: opts.expandStage,
      setActiveStepId: opts.setActiveStepId,
      setPipelineSubTab: opts.setPipelineSubTab,
      navigationIntent: navIntent,
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
      navigationIntent: navIntent,
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
      await focusStageWorkbench({
        run: refreshed,
        stageId: nextStage.id,
        selectStage: opts.selectStage,
        expandStage: opts.expandStage,
        setActiveStepId: opts.setActiveStepId,
        setPipelineSubTab: opts.setPipelineSubTab,
        substepId: "run",
        navigationIntent: navIntent,
      });
      if (await tryStartStage(nextStage.id)) return true;
      opts.showToast(readyForStageMessage(nextStage.title), "info");
      return false;
    }
  }

  const next = findNextRunnableStage(refreshed.stages, refreshed.meta);
  if (next) {
    await focusStageWorkbench({
      run: refreshed,
      stageId: next.id,
      selectStage: opts.selectStage,
      expandStage: opts.expandStage,
      setActiveStepId: opts.setActiveStepId,
      setPipelineSubTab: opts.setPipelineSubTab,
      substepId: "run",
      navigationIntent: navIntent,
    });
    if (await tryStartStage(next.id)) return true;
    opts.showToast(readyForStageMessage(next.title), "info");
    return false;
  }

  await opts.navigateToNextBlocker();
  return false;
}

/** Continue the pipeline after a stage completes: sync UI focus, then auto-run when enabled. */
export async function tryAutoContinuePipeline(
  opts: AdvancePipelineOpts & { completedStageId?: string | null },
): Promise<boolean> {
  if (opts.config?.journey_ui?.enabled === false) return false;

  let refreshed = opts.runId ? await opts.refreshRun() : opts.run;
  if (!refreshed) return false;
  if (isPipelineComplete(refreshed)) return false;

  const autoSurface = { ...opts, navigationIntent: "auto_surface" as const };

  const navigated = await syncPipelineStageFocus({ ...autoSurface, run: refreshed });
  refreshed = opts.runId ? (await opts.refreshRun()) ?? refreshed : refreshed;

  if (!isPipelineAutopilotEnabled(opts.config)) {
    return navigated;
  }

  if (isPipelineAutopilotEnabled(opts.config)) {
    const resolved = await tryAutopilotCheckpointResolution(opts);
    if (resolved) {
      refreshed = opts.runId ? (await opts.refreshRun()) ?? refreshed : refreshed;
      if (!autopilotBlocksAutoRun(refreshed, opts.config)) {
        const started = await advancePipeline({
          ...autoSurface,
          run: refreshed,
          autoRun: true,
        });
        return started || true;
      }
      return true;
    }
  }

  if (opts.completedStageId) {
    if (!shouldAutoNavigateFromStage(refreshed, opts.completedStageId, opts.config)) {
      return navigated;
    }
  }

  if (autopilotBlocksAutoRun(refreshed, opts.config)) {
    return navigated;
  }

  const autoRun = true;
  const started = await advancePipeline({ ...autoSurface, run: refreshed, autoRun });
  return started || navigated;
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
