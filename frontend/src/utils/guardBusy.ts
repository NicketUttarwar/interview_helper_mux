export type ShowToastFn = (
  msg: string,
  level?: "info" | "success" | "warning" | "error",
) => void;

/** Returns true when the click should be blocked; shows an explanatory toast. */
export function guardBusy(
  jobRunning: boolean,
  actionBusy: boolean,
  showToast: ShowToastFn,
): boolean {
  if (jobRunning) {
    showToast("A step is already running — watch the activity log.", "warning");
    return true;
  }
  if (actionBusy) {
    showToast("Checkpoint save in progress — watch Activity (Live).", "warning");
    return true;
  }
  return false;
}
