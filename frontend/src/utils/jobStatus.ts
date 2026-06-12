import type { JobState } from "../types";

export function isJobActivelyRunning(job?: JobState | null): boolean {
  return job?.status === "running" || job?.status === "running_with_warnings";
}
