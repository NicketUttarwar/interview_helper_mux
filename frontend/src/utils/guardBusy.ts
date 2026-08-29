import type { RunData } from "../types";
import { isPartialAutoCheckpoint, type PartialAutoGPublishState } from "./partialAcceleratedGuard";

export type ShowToastFn = (
  msg: string,
  level?: "info" | "success" | "warning" | "error",
) => void;

/** Returns true when the click should be blocked; shows an explanatory toast. */
export function guardBusy(
  jobRunning: boolean,
  actionBusy: boolean,
  showToast: ShowToastFn,
  opts?: {
    run?: RunData | null;
    gPublish?: PartialAutoGPublishState | null;
  },
): boolean {
  const jobBlocks =
    opts?.run != null
      ? jobRunning && !isPartialAutoCheckpoint(opts.run, opts.gPublish)
      : jobRunning;
  if (jobBlocks) {
    showToast("A step is already running — watch the activity log.", "warning");
    return true;
  }
  if (actionBusy) {
    showToast("Checkpoint save in progress — watch Activity (Live).", "warning");
    return true;
  }
  return false;
}
