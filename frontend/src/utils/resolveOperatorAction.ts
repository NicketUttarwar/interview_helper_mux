import type {
  OperatorAction,
  OperatorActionContext,
  ServerOperatorAction,
  StepMode,
} from "../types/operatorAction";
import type { RunData, StageInfo } from "../types";
import {
  findHandoffStage,
  findPendingFocusStage,
} from "./checkpoint";
import { checkpointPrimaryLabel } from "./checkpointLabels";
import { isJobActivelyRunning } from "./jobStatus";
import { resolveJobStatusContext } from "./operatorStatus";
import { parseFileCountFromMessage } from "./pendingAction";
import { findNextRunnableStage, resolvePrecleanOffer } from "./preclean";
import { buildNumberedStages, resolvePipelineNav } from "./pipelineNavigation";
import { firstTodoItem } from "./stageGuidance";
import { resolvePendingWritePaths } from "./writeApproval";

const MODE_LABELS: Record<StepMode, string> = {
  locked: "Waiting",
  idle: "Ready",
  running: "Running",
  needs_you: "Needs you",
  done: "Complete",
};

export function stepModeLabel(mode: StepMode): string {
  return MODE_LABELS[mode];
}

function stageById(run: RunData, stageId: string | null | undefined): StageInfo | null {
  if (!stageId) return null;
  return run.stages.find((s) => s.id === stageId) ?? null;
}

function stageTitle(run: RunData, stageId: string | null | undefined): string {
  return stageById(run, stageId)?.title ?? stageId ?? "Pipeline";
}

function gateHeadline(run: RunData, stageId: string, blockingReason?: string | null): string {
  switch (stageId) {
    case "transcript_review":
      return "Review speech-to-text clips";
    case "disfluency_review":
      return "Review filler clips";
    case "g1_vo_pickup":
      return "Record pickup lines";
    case "g2_flow_select":
      return "Choose output flow";
    case "analysis_profile":
      return "Verify interview profile";
    default:
      if (blockingReason === "handoff_review") return "Review AI outputs";
      return `${stageTitle(run, stageId)} needs your input`;
  }
}

function fromServerAction(
  server: ServerOperatorAction,
  run: RunData,
): OperatorAction | null {
  if (!server.mode || !server.stage_id) return null;
  const sid = server.stage_id;
  return {
    mode: server.mode,
    stageId: sid,
    substepId: server.substep_id ?? null,
    headline: server.headline ?? stageTitle(run, sid),
    subline: server.subline ?? null,
    primaryLabel: server.primary_label ?? checkpointPrimaryLabel(sid, "gate"),
    primaryKind: server.mode === "needs_you" ? "open_modal" : "none",
    primaryDisabled: server.mode === "running" || server.mode === "locked",
    modalAutoOpen: Boolean(server.modal_auto_open),
    blockingReason: undefined,
  };
}

function buildRunningAction(run: RunData, jobRunning: boolean): OperatorAction {
  const job = run.job;
  const stageId = job?.current_stage || job?.stage || null;
  const title = stageTitle(run, stageId);
  const message = job?.message?.trim();
  const shortVerb = message || "in progress";
  const progress =
    job?.stage_index != null && job?.stage_total
      ? { current: job.stage_index, total: job.stage_total, label: title }
      : undefined;

  return {
    mode: "running",
    stageId,
    substepId: "run",
    headline: `Running ${title} — ${shortVerb.replace(/\.$/, "")}`,
    subline: "Watch the activity log for progress.",
    primaryLabel: "Running…",
    primaryKind: "none",
    primaryDisabled: true,
    secondaryLabel: "View live log",
    secondaryKind: "view_logs",
    progress,
    modalAutoOpen: false,
  };
}

function buildWriteApprovalAction(run: RunData, stageId: string): OperatorAction {
  const title = stageTitle(run, stageId);
  const paths = resolvePendingWritePaths(run, stageId);
  const fileCount =
    paths.length ||
    parseFileCountFromMessage(run.job?.message) ||
    undefined;
  return {
    mode: "needs_you",
    stageId,
    substepId: `write_approval:${stageId}`,
    headline: `Review ${title} outputs before saving`,
    subline: fileCount
      ? `${fileCount} staged file${fileCount === 1 ? "" : "s"}`
      : "Preview staged outputs, then save to disk.",
    primaryLabel: checkpointPrimaryLabel(stageId, "write_approval", { fileCount }),
    primaryKind: "open_modal",
    primaryDisabled: false,
    modalAutoOpen: true,
    blockingReason: "write_approval",
  };
}

function buildReuseAction(run: RunData, stageId: string): OperatorAction {
  const title = stageTitle(run, stageId);
  const count = run.job?.reuse_candidates?.length ?? 0;
  return {
    mode: "needs_you",
    stageId,
    substepId: `stage_reuse:${stageId}`,
    headline: "Choose reuse or run fresh",
    subline: count
      ? `${count} prior run${count === 1 ? "" : "s"} with same audio`
      : `${title} — reuse from a previous execution?`,
    primaryLabel: checkpointPrimaryLabel(stageId, "stage_reuse"),
    primaryKind: "open_modal",
    primaryDisabled: false,
    modalAutoOpen: true,
    blockingReason: "stage_reuse",
  };
}

function buildHandoffAction(run: RunData, stage: StageInfo): OperatorAction {
  return {
    mode: "needs_you",
    stageId: stage.id,
    substepId: `handoff:${stage.id}`,
    headline: `Review AI outputs from ${stage.title}`,
    subline: "Skim generated files, then acknowledge to continue.",
    primaryLabel: checkpointPrimaryLabel(stage.id, "handoff"),
    primaryKind: "open_modal",
    primaryDisabled: false,
    modalAutoOpen: true,
    blockingReason: "handoff_review",
  };
}

const GATE_BLOCKING_REASONS = new Set([
  "transcript_review",
  "disfluency_review",
  "g1_vo_pickup",
  "g2_flow_select",
  "analysis_profile",
  "gate",
]);

function gateSubstepId(stageId: string, blockingReason?: string | null): string {
  if (!blockingReason) return `gate:${stageId}`;
  if (GATE_BLOCKING_REASONS.has(blockingReason)) return `gate:${stageId}`;
  return `blocked:${stageId}`;
}

function buildGateAction(
  run: RunData,
  stageId: string,
  blockingReason?: string | null,
  message?: string | null,
): OperatorAction {
  const title = stageTitle(run, stageId);
  const headline =
    run.job?.status === "gate" && message
      ? message.slice(0, 80)
      : gateHeadline(run, stageId, blockingReason);
  return {
    mode: "needs_you",
    stageId,
    substepId: gateSubstepId(stageId, blockingReason),
    headline: headline.includes(title) ? headline : `${title} — ${headline}`,
    subline: message && headline !== message ? message : "Complete the checkpoint in the review panel.",
    primaryLabel: checkpointPrimaryLabel(stageId, "gate"),
    primaryKind: "open_modal",
    primaryDisabled: false,
    modalAutoOpen: true,
    blockingReason: blockingReason ?? stageId,
  };
}

function buildLockedAction(stage: StageInfo): OperatorAction {
  const blocker = firstTodoItem(stage.guidance);
  return {
    mode: "locked",
    stageId: stage.id,
    substepId: blocker?.id ?? null,
    headline: `Waiting — complete earlier steps first`,
    subline: blocker?.label ?? "Prerequisites for this step are not met.",
    primaryLabel: "Locked",
    primaryKind: "none",
    primaryDisabled: true,
    modalAutoOpen: false,
  };
}

function buildIdleAction(run: RunData, stage: StageInfo): OperatorAction {
  return {
    mode: "idle",
    stageId: stage.id,
    substepId: "run",
    headline: `Ready — run ${stage.title}`,
    subline: "Starts this step and writes outputs when complete.",
    primaryLabel: `Run ${stage.title}`,
    primaryKind: "run_stage",
    primaryDisabled: false,
    modalAutoOpen: false,
  };
}

function buildDoneAction(
  run: RunData,
  stage: StageInfo,
  nextStage: StageInfo | null,
  nextNumber: number | null,
): OperatorAction {
  const nextTitle = nextStage?.title;
  return {
    mode: "done",
    stageId: stage.id,
    substepId: null,
    headline: `${stage.title} complete`,
    subline: nextTitle
      ? `Next — ${nextTitle}${nextNumber ? ` (step ${nextNumber})` : ""}`
      : "No further action on this step.",
    primaryLabel: nextTitle ? `Continue to ${nextTitle}` : "Step complete",
    primaryKind: nextTitle ? "continue_next" : "none",
    primaryDisabled: !nextTitle,
    modalAutoOpen: false,
  };
}

/** Global focus action for sidebar highlight and auto-navigation. */
export function resolveOperatorAction(
  run: RunData | null,
  ctx: OperatorActionContext = {},
): OperatorAction {
  const empty: OperatorAction = {
    mode: "idle",
    stageId: null,
    substepId: null,
    headline: "Open a run to see pipeline steps.",
    subline: null,
    primaryLabel: "Go to Start",
    primaryKind: "none",
    primaryDisabled: false,
    modalAutoOpen: false,
  };
  if (!run) return empty;

  const job = run.job;
  const jobRunning = Boolean(ctx.jobRunning);
  const apiGrants = ctx.apiGrants ?? {};
  const jobCtx = resolveJobStatusContext(run, jobRunning);
  const focusStageId = findPendingFocusStage(run, apiGrants);
  const serverAction = (run.journey as { active_operator_action?: ServerOperatorAction })
    ?.active_operator_action;

  if (serverAction && (!focusStageId || serverAction.stage_id === focusStageId)) {
    const mapped = fromServerAction(serverAction, run);
    if (mapped) return mapped;
  }

  if (job?.status === "interrupted") {
    const sid = job.stage || focusStageId;
    return {
      mode: "idle",
      stageId: sid,
      substepId: null,
      headline: "Run interrupted — retry this step",
      subline: job.message || "The server restarted or the job was interrupted.",
      primaryLabel: sid ? `Retry ${stageTitle(run, sid)}` : "Retry step",
      primaryKind: "run_stage",
      primaryDisabled: false,
      modalAutoOpen: false,
    };
  }

  if (jobCtx.isRunning || isJobActivelyRunning(job)) {
    return buildRunningAction(run, jobRunning);
  }

  if (jobCtx.awaitingWriteApproval) {
    const sid = job?.pending_write_stage || job?.stage || focusStageId;
    if (sid) return buildWriteApprovalAction(run, sid);
  }

  if (jobCtx.needsStageReuse && job?.stage) {
    return buildReuseAction(run, job.stage);
  }

  const blocking = run.journey?.blocking ?? run.blocking;
  if (blocking?.blocked && blocking.reason === "stage_reuse" && blocking.stage_id) {
    return buildReuseAction(run, blocking.stage_id);
  }

  const handoffStage = findHandoffStage(run);
  if (handoffStage) {
    return buildHandoffAction(run, handoffStage);
  }

  if (focusStageId) {
    const stage = stageById(run, focusStageId);
    if (stage?.status === "action_required" || job?.status === "gate") {
      return buildGateAction(
        run,
        focusStageId,
        blocking?.reason ?? stage.id,
        job?.message || blocking?.message,
      );
    }
    if (stage?.status === "awaiting_write_approval") {
      return buildWriteApprovalAction(run, focusStageId);
    }
  }

  if (blocking?.blocked && blocking.stage_id) {
    if (blocking.reason === "write_approval") {
      return buildWriteApprovalAction(run, blocking.stage_id);
    }
    if (blocking.reason === "handoff_review") {
      const st = stageById(run, blocking.stage_id);
      if (st) return buildHandoffAction(run, st);
    }
    return buildGateAction(
      run,
      blocking.stage_id,
      blocking.reason,
      blocking.message,
    );
  }

  const nav = resolvePipelineNav(run, {
    selectedStageId: ctx.selectedStageId ?? null,
    jobRunning,
    apiGrants,
  });
  const next = nav.nextStage;
  if (next) {
    if (next.status === "locked") {
      return buildLockedAction(next);
    }
    if (next.status === "pending") {
      return buildIdleAction(run, next);
    }
  }

  return {
    mode: "idle",
    stageId: null,
    substepId: null,
    headline: run.journey?.next_action || nav.statusLine || "Pipeline idle",
    subline: nav.nextLine || null,
    primaryLabel: "Open Pipeline",
    primaryKind: "none",
    primaryDisabled: true,
    modalAutoOpen: false,
  };
}

/** Action for a specific stage (sidebar selection / StepActionHeader). */
export function resolveOperatorActionForStage(
  run: RunData,
  stageId: string,
  ctx: OperatorActionContext = {},
): OperatorAction {
  const global = resolveOperatorAction(run, ctx);
  const stage = stageById(run, stageId);
  if (!stage) return global;

  const job = run.job;
  const jobRunning = Boolean(ctx.jobRunning);
  const jobCtx = resolveJobStatusContext(run, jobRunning);
  const nav = resolvePipelineNav(run, {
    selectedStageId: stageId,
    jobRunning,
    apiGrants: ctx.apiGrants ?? {},
  });
  const numbered = buildNumberedStages(run.stages);
  const entry = numbered.find((n) => n.stage.id === stageId);
  const nextEntry = nav.nextStage
    ? numbered.find((n) => n.stage.id === nav.nextStage!.id)
    : null;

  const runningStageId = job?.current_stage || job?.stage;
  if (
    (jobCtx.isRunning || isJobActivelyRunning(job)) &&
    runningStageId === stageId
  ) {
    return buildRunningAction(run, jobRunning);
  }

  if (
    jobCtx.awaitingWriteApproval &&
    (job?.pending_write_stage === stageId ||
      job?.stage === stageId ||
      stage.status === "awaiting_write_approval")
  ) {
    return buildWriteApprovalAction(run, stageId);
  }

  if (jobCtx.needsStageReuse && job?.stage === stageId) {
    return buildReuseAction(run, stageId);
  }

  if (stage.status === "done" && !run.handoff_ack?.[stageId]) {
    const handoff = findHandoffStage(run);
    if (handoff?.id === stageId) return buildHandoffAction(run, stage);
  }

  if (stage.status === "action_required" || job?.status === "gate" && job.stage === stageId) {
    const blocking = run.journey?.blocking ?? run.blocking;
    return buildGateAction(run, stageId, blocking?.reason, job?.message || blocking?.message);
  }

  if (stage.status === "locked") {
    return buildLockedAction(stage);
  }

  const precleanOffer =
    stage.id === "audio_preclean" && stage.status === "pending"
      ? resolvePrecleanOffer(stage, run.meta)
      : null;
  if (precleanOffer) {
    return {
      mode: "needs_you",
      stageId: stage.id,
      substepId: "optional:review",
      headline: "Optional audio pre-clean",
      subline: "Skip to keep the original recording, or run cleaning first.",
      primaryLabel: "View optional offer",
      primaryKind: "open_modal",
      primaryDisabled: false,
      secondaryLabel: "Skip optional step",
      secondaryKind: "skip_optional",
      modalAutoOpen: false,
    };
  }

  if (stage.status === "done") {
    const next =
      nav.nextStage?.id === stageId ? null : nav.nextStage;
    return buildDoneAction(
      run,
      stage,
      next ?? findNextRunnableStage(run.stages, run.meta),
      nextEntry?.number ?? nav.nextNumber,
    );
  }

  if (nav.nextStage?.id === stageId && stage.status === "pending") {
    const prereqs = (stage.guidance?.prerequisites || []).some((i) => i.status === "todo");
    if (prereqs) return buildLockedAction(stage);
    return buildIdleAction(run, stage);
  }

  if (global.stageId === stageId) return global;

  return {
    mode: "idle",
    stageId,
    substepId: null,
    headline: stage.title,
    subline: stage.description?.split(".")[0] ?? null,
    primaryLabel: nav.nextStage?.id === stageId ? `Run ${stage.title}` : "Select when ready",
    primaryKind: nav.nextStage?.id === stageId ? "run_stage" : "none",
    primaryDisabled: nav.nextStage?.id !== stageId,
    modalAutoOpen: false,
  };
}

export function focusStageIdFromAction(
  run: RunData | null,
  ctx: OperatorActionContext = {},
): string | null {
  return resolveOperatorAction(run, ctx).stageId;
}
