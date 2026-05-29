import type { LogEntry, RunData, StageInfo } from "../types";
import { parseLogDetail } from "./index";

export function getHandoffPathsLocal(
  stage: StageInfo,
  logTail?: LogEntry[],
): string[] {
  for (let i = (logTail || []).length - 1; i >= 0; i--) {
    const e = logTail![i];
    if (e.stage !== stage.id) continue;
    const d = parseLogDetail(e.detail);
    if (Array.isArray(d?.handoff) && d.handoff.length) return d.handoff as string[];
  }
  return [...(stage.artifacts_present || []), ...(stage.artifacts || [])].filter(
    (p, i, arr) => Boolean(p) && !p.endsWith("/") && arr.indexOf(p) === i,
  );
}

export function countPendingActions(run: RunData | null): number {
  if (!run) return 0;
  let n = 0;
  if (run.job?.status === "gate" || run.job?.status === "needs_operator") n += 1;
  n += run.stages.filter((s) => s.status === "action_required").length;
  for (const s of run.stages) {
    if (s.status !== "done") continue;
    const paths = getHandoffPathsLocal(s, run.log_tail);
    if (paths.length && !run.handoff_ack?.[s.id]) n += 1;
  }
  return n;
}

export function actionSummaryText(run: RunData | null): string | null {
  if (!run) return null;
  const job = run.job;
  const actionStage = run.stages.find((s) => s.status === "action_required");
  if (job?.status === "gate" || job?.status === "needs_operator") {
    return job.message || "Your action is required before the pipeline can continue.";
  }
  if (actionStage) {
    return `Checkpoint: ${actionStage.title} — complete the required steps.`;
  }
  const handoffStage = run.stages.find((s) => {
    if (s.status !== "done") return false;
    const paths = getHandoffPathsLocal(s, run.log_tail);
    return paths.length > 0 && !run.handoff_ack?.[s.id];
  });
  if (handoffStage) {
    return `Review outputs from ${handoffStage.title} and acknowledge to continue.`;
  }
  return null;
}

export function checkpointContinueEnabled(
  run: RunData,
  stage: StageInfo,
): boolean {
  if (run.job?.status === "needs_operator" && run.job.message?.includes("API consent")) {
    return false;
  }
  if (stage.status === "action_required") {
    if (stage.id === "g1_vo_pickup") return Boolean(run.g1_clear);
    if (stage.id === "analysis_profile") return Boolean(run.profile_verified);
    return false;
  }
  if (stage.status === "done") {
    const paths = getHandoffPathsLocal(stage, run.log_tail);
    return paths.length > 0 && !run.handoff_ack?.[stage.id];
  }
  return false;
}
