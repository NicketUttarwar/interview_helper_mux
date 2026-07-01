import type { JobState, RunData } from "../types";
import { isClarificationDeferred } from "./autopilotResolution";
import { stageAwaitingWriteApproval } from "./writeApproval";

export function isJobActivelyRunning(job?: JobState | null): boolean {
  return (
    job?.status === "running" ||
    job?.status === "running_with_warnings" ||
    isClarificationDeferred(job)
  );
}

export function isWriteApprovalSaving(job?: JobState | null): boolean {
  return isJobActivelyRunning(job) && job?.mode === "write_approval";
}

/** True when staged files are being promoted to disk (server or client save in flight). */
export function isWriteApprovalSaveInProgress(
  run: RunData | null | undefined,
  opts?: { actionBusy?: boolean; stageId?: string },
): boolean {
  if (!run) return false;
  const job = run.job;
  const sid = opts?.stageId;
  if (isWriteApprovalSaving(job)) {
    if (!sid) return true;
    const jobStage = job?.pending_write_stage || job?.stage;
    return jobStage === sid;
  }
  if (opts?.actionBusy && sid && stageAwaitingWriteApproval(run, sid)) {
    return true;
  }
  return false;
}

export function writeApprovalSaveStageId(
  run: RunData | null | undefined,
): string | null {
  if (!run) return null;
  const job = run.job;
  if (isWriteApprovalSaving(job)) {
    return job?.pending_write_stage || job?.stage || null;
  }
  return null;
}
