import type { JobState } from "../types";
import { isJobActivelyRunning } from "./jobStatus";

/** True when a poll session observed an actively running job before it stopped. */
export function jobPollObservedRunning(
  sawRunning: boolean,
  polled: JobState | null | undefined,
): boolean {
  return sawRunning || isJobActivelyRunning(polled);
}

/** Terminal poll outcomes that should not surface as toasts (stale disk state). */
export function shouldSuppressJobPollTerminalToast(
  sawRunning: boolean,
  polled: JobState | null | undefined,
): boolean {
  if (jobPollObservedRunning(sawRunning, polled)) return false;
  const status = polled?.status;
  return (
    status === "complete" ||
    status === "error" ||
    status === "gate" ||
    status === "needs_operator" ||
    status === "awaiting_write_approval" ||
    Boolean(polled?.awaiting_write_approval)
  );
}
