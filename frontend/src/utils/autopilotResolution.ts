import type { AppConfig, RunData } from "../types";
import { isPipelineAutopilotEnabled } from "./pipelineAutopilot";
import { pendingWriteInfo } from "./writeApproval";

export type AutopilotCheckpointKind = "fix_all" | "write_approval";

export interface AutopilotCheckpoint {
  kind: AutopilotCheckpointKind;
  stageId: string;
}

const fixAllAttempts = new Map<string, number>();
const MAX_FIX_ALL_ATTEMPTS = 3;

function attemptKey(runId: string, stageId: string): string {
  return `${runId}:${stageId}`;
}

export function canAttemptAutopilotFixAll(runId: string, stageId: string): boolean {
  return (fixAllAttempts.get(attemptKey(runId, stageId)) ?? 0) < MAX_FIX_ALL_ATTEMPTS;
}

export function recordAutopilotFixAllAttempt(runId: string, stageId: string): void {
  const key = attemptKey(runId, stageId);
  fixAllAttempts.set(key, (fixAllAttempts.get(key) ?? 0) + 1);
}

export function clearAutopilotFixAllAttempts(runId: string, stageId: string): void {
  fixAllAttempts.delete(attemptKey(runId, stageId));
}

export function resetAutopilotAttemptsForRun(runId: string): void {
  for (const key of [...fixAllAttempts.keys()]) {
    if (key.startsWith(`${runId}:`)) {
      fixAllAttempts.delete(key);
    }
  }
}

function jobCanAutopilotFix(run: RunData, stageId: string): boolean {
  const job = run.job;
  if (!job) return false;
  if (job.stage && job.stage !== stageId) return false;
  if (job.can_fix_all === false) return false;
  if (job.can_fix_all === true || job.bridge_eligible === true) return true;
  const open = Number(job.itr_open_blocking ?? job.itr_blocking_count ?? 0);
  return open > 0;
}

/** Next checkpoint autopilot can clear without operator clicks. */
export function resolveAutopilotCheckpoint(
  run: RunData | null,
  config?: AppConfig | null,
): AutopilotCheckpoint | null {
  if (!run || !isPipelineAutopilotEnabled(config)) return null;

  const write = pendingWriteInfo(run);
  if (write?.paths.length) {
    return { kind: "write_approval", stageId: write.stageId };
  }

  const job = run.job;
  const blocking = run.journey?.blocking ?? run.blocking;
  const stageId =
    job?.pending_write_stage ||
    job?.stage ||
    (blocking?.stage_id && blocking.stage_id) ||
    null;
  if (!stageId) return null;

  if (
    job?.status === "awaiting_write_approval" ||
    job?.awaiting_write_approval ||
    blocking?.reason === "write_approval" ||
    run.stages.some((s) => s.id === stageId && s.status === "awaiting_write_approval")
  ) {
    return { kind: "write_approval", stageId };
  }

  if (
    job?.status === "needs_clarification" ||
    blocking?.reason === "artifact_clarification"
  ) {
    if (jobCanAutopilotFix(run, stageId)) {
      return { kind: "fix_all", stageId };
    }
    return null;
  }

  if (job?.status === "gate" || blocking?.reason === "llm_gate") {
    if (jobCanAutopilotFix(run, stageId)) {
      return { kind: "fix_all", stageId };
    }
    return null;
  }

  return null;
}

export function autopilotHidesReviewGate(
  run: RunData | null,
  stageId: string,
  config?: AppConfig | null,
): boolean {
  const checkpoint = resolveAutopilotCheckpoint(run, config);
  return Boolean(checkpoint && checkpoint.stageId === stageId);
}
