import type { LogEntry, RunData, StageInfo } from "../types";
import { isCustomRunArtifactPath } from "../generated/customRunArtifactPaths";
import { parseLogDetail } from "./index";
import { resolveJobStatusContext, reuseStatusLine } from "./operatorStatus";
import { countRequiredAttention, topAttentionItem } from "./attentionQueue";
import { findNextRunnableStage } from "./preclean";
import { firstUpstreamBlocker } from "./stageOutputs";
import { isStageHidden } from "./stageVisibility";
import { gateFocusStageId } from "./gateFocus";

export { stageTitleById as stageTitleForId } from "./logDisplay";
export { isCustomRunArtifactPath } from "../generated/customRunArtifactPaths";
export { gateFocusStageId, operatorGateFocusStage, upstreamStageFromGateMessage } from "./gateFocus";

export function filterCustomRunHandoffPaths(paths: string[]): string[] {
  return paths.filter(isCustomRunArtifactPath);
}

function filterCompleteHandoffPaths(stage: StageInfo, paths: string[]): string[] {
  const custom = filterCustomRunHandoffPaths(paths);
  if (stage.handoff_paths?.length) {
    const serverSet = new Set(stage.handoff_paths);
    return custom.filter((p) => serverSet.has(p));
  }
  const statusMap = stage.artifacts_status || {};
  return custom.filter((p) => statusMap[p] === "complete");
}

export function getHandoffPathsLocal(
  stage: StageInfo,
  logTail?: LogEntry[],
): string[] {
  if (stage.handoff_paths?.length) {
    return filterCustomRunHandoffPaths(stage.handoff_paths);
  }
  for (let i = (logTail || []).length - 1; i >= 0; i--) {
    const e = logTail![i];
    if (e.stage !== stage.id) continue;
    const d = parseLogDetail(e.detail);
    if (Array.isArray(d?.handoff) && d.handoff.length) {
      return filterCompleteHandoffPaths(stage, d.handoff as string[]);
    }
  }
  return filterCompleteHandoffPaths(
    stage,
    [...(stage.artifacts_present || []), ...(stage.artifacts || [])].filter(
      (p, i, arr) => Boolean(p) && !p.endsWith("/") && arr.indexOf(p) === i,
    ),
  );
}

/** Stage id the operator should focus on for checkpoints, gates, or job pause. */
export function resolveOperatorFocusStageId(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): string | null {
  if (!run) return null;
  const top = topAttentionItem(run, grants);
  if (top?.stageId) return top.stageId;
  return findPendingFocusStage(run, grants);
}

/** Stage id the operator should focus on for checkpoints, gates, or job pause. */
export function findPendingFocusStage(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): string | null {
  if (!run) return null;

  if (run.transcript_review_pending) return "transcript_review";
  if (run.gap_framing_decision_pending) return "missing_framing";

  const blocking = run.journey?.blocking ?? run.blocking;
  if (blocking?.blocked && blocking.stage_id) {
    const blockedStage = run.stages.find((s) => s.id === blocking.stage_id);
    if (!(blockedStage && isStageHidden(blockedStage))) {
      const reason = blocking.reason || "";
      if (
        reason === "transcript_review" ||
        reason === "g1_vo_pickup" ||
        reason === "g1_5_preview_pickup" ||
        reason === "pickup_speaker" ||
        reason === "llm_gate"
      ) {
        return blocking.stage_id;
      }
    }
  }

  if (run.job?.status === "gate") {
    const gateStage = gateFocusStageId(run.job);
    if (gateStage) return gateStage;
  }
  if (run.job?.needs_stage_reuse && run.job.stage) return run.job.stage;
  if (
    run.job?.status === "needs_operator" &&
    !isApiConsentJobPending(run, grants) &&
    run.job.stage
  ) {
    return run.job.stage;
  }

  if (blocking?.blocked && blocking.stage_id) {
    const blockedStage = run.stages.find((s) => s.id === blocking.stage_id);
    if (!(blockedStage && isStageHidden(blockedStage))) {
      return blocking.stage_id;
    }
  }

  const next = findNextRunnableStage(run.stages, run.meta);
  if (
    next &&
    (next.status === "pending" ||
      next.status === "incomplete" ||
      next.status === "action_required")
  ) {
    const blocker = firstUpstreamBlocker(run.stages, next.id, run.meta);
    if (blocker) return blocker.id;
    return next.id;
  }

  return null;
}

export function continueHintForStage(stageId: string, run?: RunData | null): string {
  const blockingMsg = run?.journey?.blocking?.message || run?.blocking?.message;
  switch (stageId) {
    case "transcript_review": {
      const n = blockingMsg?.match(/Review (\d+) ranked STT/)?.[1];
      return n
        ? `${n} ranked clip(s) remaining — lowest confidence first.`
        : "Complete transcript review in the panel above (save clips or use Complete review).";
    }
    case "g1_vo_pickup": {
      const n =
        run?.g1_missing?.length ||
        (blockingMsg?.match(/Record (\d+) pickup/)?.[1]
          ? parseInt(blockingMsg.match(/Record (\d+) pickup/)![1], 10)
          : undefined);
      return n
        ? `${n} pickup line(s) remaining — record or upload each line above.`
        : "Record or upload every pickup line listed above.";
    }
    case "assembly_preview":
      return "Listen to the speech + VO preview before sound spend.";
    case "sonic_context_build":
      return "Review sonic context tags and scenario policy in the panel above.";
    case "sfx_prompt_craft":
      return "Approve MMAudio prompts and complete listen checks above.";
    case "mmaudio_sfx":
      return "Listen to outputs and pass or fail the sound check above.";
    case "framing_posture_decide":
      return "Advisory framing posture LLM runs before G-Framing — operator Yes/No remains authoritative (2M).";
    case "vo_line_adjudicate":
      return "Smart per-line VO adjudication before synthesis — review activity log for drops and rewrites.";
    case "missing_framing":
      return "Confirm G-Framing choice — LLM recommendation is advisory only.";
    default:
      return "Complete the required steps above before continuing.";
  }
}

/** v2 disables mid-stage AI output handoffs. */
export function handoffBetweenStagesEnabled(_run: RunData | null): boolean {
  return false;
}

export function findHandoffStage(_run: RunData | null): StageInfo | null {
  return null;
}

/** External APIs are auto-consented — consent never blocks the operator UI. */
export function isApiConsentJobPending(
  _run: RunData | null,
  _grants: Record<string, boolean> = {},
): boolean {
  return false;
}

export function countPendingActions(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): number {
  return countRequiredAttention(run, grants);
}

export function actionSummaryText(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): string | null {
  if (!run) return null;
  const job = run.job;
  const ctx = resolveJobStatusContext(run, false);
  if (job?.status === "gate") {
    return job.message || "Action required before the pipeline can continue.";
  }
  if (ctx.needsStageReuse) {
    return job?.message || reuseStatusLine(run, job).replace("?", ".");
  }
  if (job?.status === "needs_operator" && isApiConsentJobPending(run, grants)) {
    return job.message || "Action required before the pipeline can continue.";
  }
  if (ctx.actionRequiredStage) {
    return `${ctx.actionRequiredStage.title} — complete the required steps.`;
  }
  return null;
}

export function checkpointContinueLabel(
  _run: RunData,
  _stage: StageInfo,
  _grants: Record<string, boolean> = {},
): string {
  return "Continue to next step";
}

export function checkpointContinueEnabled(
  run: RunData,
  stage: StageInfo,
  grants: Record<string, boolean> = {},
): boolean {
  if (isApiConsentJobPending(run, grants)) {
    return false;
  }
  if (stage.status === "action_required") {
    if (stage.id === "g1_vo_pickup") return Boolean(run.g1_clear);
    return false;
  }
  if (stage.status === "automation_pending") {
    return false;
  }
  return false;
}
