import type { JobState } from "../types";
import { isClarificationDeferred } from "./autopilotResolution";

export function isJobActivelyRunning(job?: JobState | null): boolean {
  return (
    job?.status === "running" ||
    job?.status === "running_with_warnings" ||
    isClarificationDeferred(job)
  );
}

/** @deprecated v2 no longer surfaces write-approval checkpoints in the GUI. */
export function isWriteApprovalSaving(_job?: JobState | null): boolean {
  return false;
}

/** @deprecated v2 no longer surfaces write-approval checkpoints in the GUI. */
export function isWriteApprovalSaveInProgress(
  _run?: unknown,
  _opts?: { actionBusy?: boolean; stageId?: string },
): boolean {
  return false;
}

/** @deprecated v2 no longer surfaces write-approval checkpoints in the GUI. */
export function writeApprovalSaveStageId(_run?: unknown): string | null {
  return null;
}
