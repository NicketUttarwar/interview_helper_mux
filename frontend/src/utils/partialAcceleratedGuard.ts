import type { RunData } from "../types";

export interface PartialAutoGPublishState {
  pending?: boolean;
  package_ready?: boolean;
  skipped?: boolean;
  already_uploaded_count?: number;
}

export function isPartialAcceleratedRun(run: RunData | null | undefined): boolean {
  if (!run?.meta) return false;
  return (
    run.meta.run_mode === "partially-accelerated" ||
    Boolean(run.meta.partial_auto)
  );
}

/** Operator checkpoint — overlay lifts so transcript review or G-Publish is interactive. */
export function isPartialAutoCheckpoint(
  run: RunData | null | undefined,
  gPublish: PartialAutoGPublishState | null | undefined,
): boolean {
  if (!run) return false;
  if (run.journey?.blocking?.reason === "transcript_review") return true;
  if (run.job?.status === "needs_operator") return true;
  if (gPublish?.pending && gPublish.package_ready && !gPublish.skipped) return true;
  return false;
}

export function shouldShowAcceleratedRunOverlay(
  run: RunData | null | undefined,
  gPublish: PartialAutoGPublishState | null | undefined,
  opts?: { jobRunning?: boolean },
): boolean {
  if (!isPartialAcceleratedRun(run)) return false;
  if (run?.meta?.partial_auto_complete === true) return false;
  if (isPartialAutoCheckpoint(run, gPublish)) return false;

  const driverActive = run?.meta?.partial_auto_driver_active;
  if (driverActive === false && !opts?.jobRunning) return false;

  return driverActive === true || Boolean(opts?.jobRunning) || driverActive == null;
}
