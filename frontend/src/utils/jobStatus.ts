import type { JobState } from "../types";

export function isJobActivelyRunning(job?: JobState | null): boolean {
  return job?.status === "running" || job?.status === "running_with_warnings";
}

export function isWriteApprovalSaving(job?: JobState | null): boolean {
  return isJobActivelyRunning(job) && job?.mode === "write_approval";
}
