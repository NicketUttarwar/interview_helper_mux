import type { JobState, StageInfo, StageStatus } from "../types";
import { isClarificationDeferred } from "./autopilotResolution";

export function isJobActivelyRunning(job?: JobState | null): boolean {
  return (
    job?.status === "running" ||
    job?.status === "running_with_warnings" ||
    isClarificationDeferred(job)
  );
}

const PRESERVE_STATUS = new Set<StageStatus>([
  "action_required",
  "awaiting_write_approval",
]);

/** Merge GET /job live progress into the last GET /runs stage snapshot. */
export function applyLiveJobToStages(
  stages: StageInfo[] | undefined,
  job: JobState | null | undefined,
): StageInfo[] {
  if (!stages?.length || !job) return stages ?? [];
  const progressById = new Map(
    (job.stage_progress || []).map((row) => [row.id, row.status]),
  );
  const done = new Set(job.stages_done || []);
  const running = isJobActivelyRunning(job);
  const current = job.current_stage || job.stage || null;
  const parent = job.parent_stage || null;

  let changed = false;
  const next = stages.map((stage) => {
    if (PRESERVE_STATUS.has(stage.status)) return stage;
    const live = progressById.get(stage.id);
    const isCurrent = running && (stage.id === current || stage.id === parent);
    if (isCurrent) {
      if (stage.status === "done" || stage.status === "locked") {
        changed = true;
        return { ...stage, status: "pending" as const };
      }
      return stage;
    }
    const finished = live === "done" || done.has(stage.id);
    if (
      finished &&
      (stage.status === "pending" ||
        stage.status === "locked" ||
        stage.status === "incomplete")
    ) {
      changed = true;
      return { ...stage, status: "done" as const };
    }
    if (live === "pending" && stage.status === "done" && running && current === stage.id) {
      changed = true;
      return { ...stage, status: "pending" as const };
    }
    return stage;
  });
  return changed ? next : stages;
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
