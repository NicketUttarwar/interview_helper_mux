import type {
  OperatorAction,
  OperatorActionContext,
  ServerOperatorAction,
  StepMode,
} from "../types/operatorAction";
import type { RunData, StageInfo } from "../types";
import { findPendingFocusStage } from "./checkpoint";
import { checkpointPrimaryLabel } from "./checkpointLabels";
import { isJobActivelyRunning } from "./jobStatus";
import { isPartialAutoCheckpoint } from "./partialAcceleratedGuard";
import { resolveJobStatusContext } from "./operatorStatus";
import {
  findNextRunnableStage,
  isOptionalStageSkipped,
  resolvePrecleanOffer,
} from "./preclean";
import { buildNumberedStages, resolvePipelineNav } from "./pipelineNavigation";
import {
  firstStageHealthTodoItem,
  firstUpstreamTodoItem,
} from "./stageGuidance";
import { stageHasCommittedOutputs, stageIncompleteReason, firstUpstreamBlocker } from "./stageOutputs";
import { isStageHidden } from "./stageVisibility";

const MODE_LABELS: Record<StepMode, string> = {
  locked: "Waiting",
  idle: "Ready",
  running: "Running",
  needs_you: "Needs you",
  done: "Complete",
  error: "Failed",
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

function gateHeadline(run: RunData, stageId: string): string {
  switch (stageId) {
    case "transcript_review":
      return "Review speech-to-text clips";
    case "g1_vo_pickup":
      return "Record pickup lines";
    case "g1_5_preview_pickup":
      return "Re-record post-preview pickup lines";
    case "source_topology_build":
      return "Confirm source topology";
    case "missing_framing":
      return "Confirm gap pickup speaker";
    default:
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

function buildErrorAction(run: RunData): OperatorAction {
  const job = run.job;
  const stageId = job?.stage || job?.current_stage || null;
  const title = stageTitle(run, stageId);
  const msg = job?.last_error?.message || job?.message || "See activity log for details.";
  return {
    mode: "error",
    stageId,
    substepId: "error",
    headline: stageId ? `${title} failed` : "Pipeline step failed",
    subline: msg,
    primaryLabel: stageId ? `Retry ${title}` : "Retry step",
    primaryKind: stageId ? "run_stage" : "none",
    primaryDisabled: !stageId,
    secondaryLabel: "View live log",
    secondaryKind: "view_logs",
    modalAutoOpen: false,
  };
}

function buildRunningAction(run: RunData, _jobRunning: boolean): OperatorAction {
  const job = run.job;
  const stageId = job?.current_stage || job?.stage || null;
  const title = stageTitle(run, stageId);
  const message = job?.message?.trim();
  const shortVerb = message || "in progress";
  const intraProgress =
    job?.step_index != null && job?.step_total && job.step_total > 1
      ? {
          current: job.step_index,
          total: job.step_total,
          label: job.phase?.replace(/_/g, " ") ?? title,
        }
      : undefined;
  const progress =
    intraProgress ??
    (job?.stage_index != null && job?.stage_total
      ? { current: job.stage_index, total: job.stage_total, label: title }
      : undefined);

  return {
    mode: "running",
    stageId,
    substepId: "run",
    headline: `Running ${title} — ${shortVerb.replace(/\.$/, "")}`,
    subline: message || "Watch the activity log for progress.",
    primaryLabel: "Running…",
    primaryKind: "none",
    primaryDisabled: true,
    secondaryLabel: "View live log",
    secondaryKind: "view_logs",
    progress,
    modalAutoOpen: false,
  };
}

function buildReuseAction(run: RunData, stageId: string): OperatorAction {
  const title = stageTitle(run, stageId);
  const count = run.job?.reuse_candidates?.length ?? 0;
  return {
    mode: "needs_you",
    stageId,
    substepId: `stage_reuse:${stageId}`,
    headline: `${title} — reuse or run fresh`,
    subline: count
      ? `${count} prior run${count === 1 ? "" : "s"} with matching audio — choose below.`
      : "Pick a prior run or run this step fresh using the buttons below.",
    primaryLabel: "Show reuse options",
    primaryKind: "open_modal",
    primaryDisabled: false,
    modalAutoOpen: false,
    blockingReason: "stage_reuse",
  };
}

function buildPrecleanAction(stage: StageInfo): OperatorAction {
  const isPickup = stage.id === "g1_vo_pickup";
  return {
    mode: "needs_you",
    stageId: stage.id,
    substepId: isPickup ? "preclean:pickup" : "preclean:run",
    headline: isPickup ? "Optional pickup cleaning" : "Run audio pre-clean",
    subline: isPickup
      ? "Remove background noise from new pickup recordings before VO ingest."
      : "Clean background noise on the source recording before ingest.",
    primaryLabel: isPickup ? "Run pickup cleaning" : "Run audio cleaning",
    primaryKind: "open_modal",
    primaryDisabled: false,
    modalAutoOpen: false,
    blockingReason: "preclean",
  };
}

const GATE_BLOCKING_REASONS = new Set([
  "transcript_review",
  "g1_vo_pickup",
  "g1_5_preview_pickup",
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
      : gateHeadline(run, stageId);
  return {
    mode: "needs_you",
    stageId,
    substepId: gateSubstepId(stageId, blockingReason),
    headline: headline.includes(title) ? headline : `${title} — ${headline}`,
    subline: message && headline !== message ? message : "Complete the checkpoint in the review panel.",
    primaryLabel: checkpointPrimaryLabel(stageId, "gate"),
    primaryKind: "open_modal",
    primaryDisabled: false,
    modalAutoOpen: false,
    blockingReason: blockingReason ?? stageId,
  };
}

function buildLockedAction(stage: StageInfo): OperatorAction {
  const health = firstStageHealthTodoItem(stage.guidance);
  const blocker = firstUpstreamTodoItem(stage.guidance);
  if (health && !blocker) {
    return {
      mode: "error",
      stageId: stage.id,
      substepId: health.id,
      headline: `${stage.title} needs a re-run`,
      subline: health.label,
      primaryLabel: `Re-run ${stage.title}`,
      primaryKind: "run_stage",
      primaryDisabled: false,
      modalAutoOpen: false,
    };
  }
  const todo = blocker ?? health;
  return {
    mode: "locked",
    stageId: stage.id,
    substepId: todo?.id ?? null,
    headline: `Waiting — complete earlier steps first`,
    subline: todo?.label ?? "Prerequisites for this step are not met.",
    primaryLabel: "Locked",
    primaryKind: "none",
    primaryDisabled: true,
    modalAutoOpen: false,
  };
}

function runStageBlocked(run: RunData, stageId: string): StageInfo | null {
  const upstream = firstUpstreamBlocker(run.stages, stageId, run.meta);
  if (upstream && upstream.id !== stageId) return upstream;
  const blocking = run.journey?.blocking ?? run.blocking;
  if (blocking?.blocked && blocking.stage_id && blocking.stage_id !== stageId) {
    const blocker = stageById(run, blocking.stage_id);
    if (blocker) return blocker;
  }
  const job = run.job;
  if (
    job?.status === "gate" ||
    job?.status === "needs_clarification"
  ) {
    const gateStage = job.pending_write_stage || job.stage;
    if (gateStage && gateStage !== stageId) {
      const blocker = stageById(run, gateStage);
      if (blocker) return blocker;
    }
  }
  return null;
}

function buildIdleAction(run: RunData, stage: StageInfo): OperatorAction {
  const blocker = runStageBlocked(run, stage.id);
  return {
    mode: "idle",
    stageId: stage.id,
    substepId: "run",
    headline: blocker ? `Blocked — finish ${blocker.title} first` : `Ready — run ${stage.title}`,
    subline: blocker
      ? stageIncompleteReason(blocker) || "Complete the upstream stage before running this one."
      : "Starts this step and writes outputs when complete.",
    primaryLabel: `Run ${stage.title}`,
    primaryKind: "run_stage",
    primaryDisabled: Boolean(blocker),
    modalAutoOpen: false,
  };
}

function buildDoneAction(
  _run: RunData,
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

  if (job?.status === "stalled") {
    const sid = job.stage || focusStageId;
    return {
      mode: "idle",
      stageId: sid,
      substepId: null,
      headline: "Stage stalled — retry this step",
      subline: job.message || "No progress recently — safe to re-run.",
      primaryLabel: sid ? `Retry ${stageTitle(run, sid)}` : "Retry step",
      primaryKind: "run_stage",
      primaryDisabled: false,
      modalAutoOpen: false,
    };
  }

  if (job?.status === "error") {
    return buildErrorAction(run);
  }

  const atCheckpoint = isPartialAutoCheckpoint(run, ctx.gPublish);
  if (!atCheckpoint && (jobCtx.isRunning || isJobActivelyRunning(job))) {
    return buildRunningAction(run, jobRunning);
  }

  if (job?.status === "gate" && job.stage) {
    const blocking = run.journey?.blocking ?? run.blocking;
    return buildGateAction(
      run,
      job.stage,
      blocking?.reason,
      job.message || blocking?.message,
    );
  }

  if (jobCtx.needsStageReuse && job?.stage) {
    return buildReuseAction(run, job.stage);
  }

  const blocking = run.journey?.blocking ?? run.blocking;
  if (blocking?.blocked && blocking.reason === "stage_reuse" && blocking.stage_id) {
    return buildReuseAction(run, blocking.stage_id);
  }

  if (focusStageId) {
    const stage = stageById(run, focusStageId);
    if (stage?.status === "action_required" || job?.status === "gate") {
      return buildGateAction(
        run,
        focusStageId,
        blocking?.reason ?? stage?.id ?? focusStageId,
        job?.message || blocking?.message,
      );
    }
  }

  if (blocking?.blocked && blocking.stage_id) {
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
    if (
      next.status === "pending" &&
      !isOptionalStageSkipped(next, run.meta) &&
      resolvePrecleanOffer(next, run.meta)
    ) {
      return buildPrecleanAction(next);
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
  if (isStageHidden(stage)) {
    const next = findNextRunnableStage(run.stages, run.meta);
    return buildDoneAction(run, stage, next ?? null, null);
  }

  const job = run.job;
  const jobRunning = Boolean(ctx.jobRunning);
  const jobCtx = resolveJobStatusContext(run, jobRunning);
  const nav = resolvePipelineNav(run, {
    selectedStageId: stageId,
    jobRunning,
    apiGrants: ctx.apiGrants ?? {},
  });
  const numbered = buildNumberedStages(run.stages);
  const nextEntry = nav.nextStage
    ? numbered.find((n) => n.stage.id === nav.nextStage!.id)
    : null;

  const runningStageId = job?.current_stage || job?.stage;
  if (job?.status === "error" && runningStageId === stageId) {
    return buildErrorAction(run);
  }

  const atCheckpoint = isPartialAutoCheckpoint(run, ctx.gPublish);
  if (
    !atCheckpoint &&
    (jobCtx.isRunning || isJobActivelyRunning(job)) &&
    runningStageId === stageId
  ) {
    return buildRunningAction(run, jobRunning);
  }

  if (job?.status === "gate" && job.stage === stageId) {
    const blocking = run.journey?.blocking ?? run.blocking;
    return buildGateAction(run, stageId, blocking?.reason, job?.message || blocking?.message);
  }

  if (jobCtx.needsStageReuse && job?.stage === stageId) {
    return buildReuseAction(run, stageId);
  }

  if (stage.status === "action_required" || job?.status === "gate" && job.stage === stageId) {
    const blocking = run.journey?.blocking ?? run.blocking;
    return buildGateAction(run, stageId, blocking?.reason, job?.message || blocking?.message);
  }

  if (stage.status === "locked") {
    return buildLockedAction(stage);
  }

  const precleanOffer =
    !isOptionalStageSkipped(stage, run.meta)
      ? resolvePrecleanOffer(stage, run.meta)
      : null;
  if (precleanOffer) {
    if (
      stage.id === "audio_preclean" &&
      stage.status === "pending"
    ) {
      return buildPrecleanAction(stage);
    }
    if (stage.id === "g1_vo_pickup" && stage.status === "done") {
      return buildPrecleanAction(stage);
    }
  }

  if (stage.stage_output_mode === "optional_skipped") {
    const next =
      nav.nextStage?.id === stageId
        ? null
        : (nav.nextStage ?? findNextRunnableStage(run.stages, run.meta) ?? null);
    return buildDoneAction(
      run,
      stage,
      next,
      nextEntry?.number ?? nav.nextNumber,
    );
  }

  if (
    stage.status === "incomplete" ||
    (stage.status === "done" && !stageHasCommittedOutputs(stage))
  ) {
    const upstream = firstUpstreamBlocker(run.stages, stageId, run.meta);
    if (upstream) {
      return {
        mode: "locked",
        stageId: stage.id,
        substepId: upstream.id,
        headline: `Waiting — finish ${upstream.title} first`,
        subline:
          stageIncompleteReason(stage) ||
          "This step is not ready yet. Continue with earlier pipeline steps.",
        primaryLabel: "Locked",
        primaryKind: "none",
        primaryDisabled: true,
        modalAutoOpen: false,
      };
    }
    const reason = stageIncompleteReason(stage);
    return {
      mode: "error",
      stageId: stage.id,
      substepId: "incomplete",
      headline: `${stage.title} incomplete`,
      subline: reason || "Required output files are missing. Rerun this step.",
      primaryLabel: `Rerun ${stage.title}`,
      primaryKind: "run_stage",
      primaryDisabled: false,
      modalAutoOpen: false,
    };
  }

  if (stage.status === "done") {
    const next =
      nav.nextStage?.id === stageId
        ? null
        : (nav.nextStage ?? findNextRunnableStage(run.stages, run.meta) ?? null);
    return buildDoneAction(
      run,
      stage,
      next,
      nextEntry?.number ?? nav.nextNumber,
    );
  }

  if (nav.nextStage?.id === stageId && stage.status === "pending") {
    const upstreamBlocked = (stage.guidance?.prerequisites || []).some(
      (i) => i.status === "todo" && (i.category || "upstream") === "upstream",
    );
    if (upstreamBlocked) return buildLockedAction(stage);
    const health = firstStageHealthTodoItem(stage.guidance);
    if (health) {
      return {
        mode: "error",
        stageId: stage.id,
        substepId: health.id,
        headline: `${stage.title} needs a re-run`,
        subline: health.label,
        primaryLabel: `Re-run ${stage.title}`,
        primaryKind: "run_stage",
        primaryDisabled: false,
        modalAutoOpen: false,
      };
    }
    const action = buildIdleAction(run, stage);
    return action;
  }

  if (global.stageId === stageId) return global;

  const blocker = runStageBlocked(run, stageId);
  return {
    mode: "idle",
    stageId,
    substepId: null,
    headline: stage.title,
    subline: blocker
      ? `Blocked by ${blocker.title} — complete upstream outputs first.`
      : stage.description?.split(".")[0] ?? null,
    primaryLabel: nav.nextStage?.id === stageId ? `Run ${stage.title}` : "Select when ready",
    primaryKind: nav.nextStage?.id === stageId ? "run_stage" : "none",
    primaryDisabled: nav.nextStage?.id !== stageId || Boolean(blocker),
    modalAutoOpen: false,
  };
}

export function focusStageIdFromAction(
  run: RunData | null,
  ctx: OperatorActionContext = {},
): string | null {
  return resolveOperatorAction(run, ctx).stageId;
}
