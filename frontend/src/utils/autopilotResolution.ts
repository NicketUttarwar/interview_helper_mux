import type { AppConfig, JobState, RunData } from "../types";
import { isPipelineAutopilotEnabled } from "./pipelineAutopilot";
import { isFullAutopilotEnabled } from "./fullAutopilot";

export type AutopilotCheckpointKind = "fix_all" | "write_approval";

export interface AutopilotCheckpoint {
  kind: AutopilotCheckpointKind;
  stageId: string;
}

const checkpointAttempts = new Map<string, number>();
const MAX_FIX_ALL_ATTEMPTS = 3;
const MAX_WRITE_APPROVAL_ATTEMPTS = 3;

function attemptKey(runId: string, stageId: string, kind: AutopilotCheckpointKind): string {
  return `${runId}:${stageId}:${kind}`;
}

export function isClarificationDeferred(job?: JobState | null): boolean {
  return Boolean(job?.clarification_pending);
}

export function canAttemptAutopilotCheckpoint(
  runId: string,
  checkpoint: AutopilotCheckpoint,
): boolean {
  const cap =
    checkpoint.kind === "write_approval" ? MAX_WRITE_APPROVAL_ATTEMPTS : MAX_FIX_ALL_ATTEMPTS;
  return (checkpointAttempts.get(attemptKey(runId, checkpoint.stageId, checkpoint.kind)) ?? 0) < cap;
}

/** @deprecated Use canAttemptAutopilotCheckpoint */
export function canAttemptAutopilotFixAll(runId: string, stageId: string): boolean {
  return canAttemptAutopilotCheckpoint(runId, { kind: "fix_all", stageId });
}

export function recordAutopilotCheckpointAttempt(
  runId: string,
  checkpoint: AutopilotCheckpoint,
): void {
  const key = attemptKey(runId, checkpoint.stageId, checkpoint.kind);
  checkpointAttempts.set(key, (checkpointAttempts.get(key) ?? 0) + 1);
}

export function recordAutopilotFixAllAttempt(runId: string, stageId: string): void {
  recordAutopilotCheckpointAttempt(runId, { kind: "fix_all", stageId });
}

export function recordAutopilotWriteApprovalAttempt(runId: string, stageId: string): void {
  recordAutopilotCheckpointAttempt(runId, { kind: "write_approval", stageId });
}

export function clearAutopilotCheckpointAttempts(
  runId: string,
  stageId: string,
  kind?: AutopilotCheckpointKind,
): void {
  if (kind) {
    checkpointAttempts.delete(attemptKey(runId, stageId, kind));
    return;
  }
  checkpointAttempts.delete(attemptKey(runId, stageId, "fix_all"));
  checkpointAttempts.delete(attemptKey(runId, stageId, "write_approval"));
}

export function clearAutopilotFixAllAttempts(runId: string, stageId: string): void {
  clearAutopilotCheckpointAttempts(runId, stageId, "fix_all");
}

export function resetAutopilotAttemptsForRun(runId: string): void {
  for (const key of [...checkpointAttempts.keys()]) {
    if (key.startsWith(`${runId}:`)) {
      checkpointAttempts.delete(key);
    }
  }
}

function hasLegacyItrBlockingIssues(run: RunData, stageId: string): boolean {
  const job = run.job;
  if (job?.stage && job.stage !== stageId) return false;
  const open = Number(job?.itr_open_blocking ?? job?.itr_blocking_count ?? 0);
  if (open > 0) return true;
  const blocking = run.journey?.blocking ?? run.blocking;
  return Boolean(
    blocking?.blocked &&
      blocking.stage_id === stageId &&
      blocking.reason === "artifact_clarification",
  );
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

  if (isClarificationDeferred(run.job)) return null;

  const job = run.job;
  const blocking = run.journey?.blocking ?? run.blocking;
  const stageId =
    job?.pending_write_stage ||
    job?.stage ||
    (blocking?.stage_id && blocking.stage_id) ||
    null;
  if (!stageId) return null;

  if (!isFullAutopilotEnabled(config)) {
    const itrBlocked = hasLegacyItrBlockingIssues(run, stageId);
    const needsClarification =
      job?.status === "needs_clarification" || blocking?.reason === "artifact_clarification";
    const llmGate = job?.status === "gate" || blocking?.reason === "llm_gate";

    if (itrBlocked || needsClarification || llmGate) {
      if (jobCanAutopilotFix(run, stageId) || itrBlocked || needsClarification) {
        const fixCheckpoint: AutopilotCheckpoint = { kind: "fix_all", stageId };
        if (canAttemptAutopilotCheckpoint(run.run_id, fixCheckpoint)) {
          return fixCheckpoint;
        }
      }
    }
  }

  return null;
}

export function autopilotHidesReviewGate(
  run: RunData | null,
  stageId: string,
  config?: AppConfig | null,
): boolean {
  if (isFullAutopilotEnabled(config)) {
    const blocking = run?.journey?.blocking ?? run?.blocking;
    if (
      blocking?.stage_id === stageId &&
      blocking.reason === "operator_decisions"
    ) {
      return false;
    }
    if (Number(run?.job?.pending_decision_count ?? 0) > 0 && run?.job?.stage === stageId) {
      return false;
    }
  }
  const checkpoint = resolveAutopilotCheckpoint(run, config);
  return Boolean(
    checkpoint && checkpoint.kind === "fix_all" && checkpoint.stageId === stageId,
  );
}
