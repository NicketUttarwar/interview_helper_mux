import type { RunData } from "../types";
import { findHandoffStage, findPendingFocusStage } from "./checkpoint";
import { resolveJobStatusContext } from "./operatorStatus";

export type PendingActionKind =
  | "write_approval"
  | "stage_reuse"
  | "gate"
  | "handoff"
  | "blocked";

export interface PendingAction {
  kind: PendingActionKind;
  stageId: string;
  stageTitle: string;
  title: string;
  message: string;
  primaryLabel: string;
  fileCount?: number;
}

function parseFileCountFromMessage(msg?: string): number | undefined {
  if (!msg) return undefined;
  const match = msg.match(/\((\d+)\s+file/i);
  return match ? parseInt(match[1], 10) : undefined;
}

export { parseFileCountFromMessage };

/** Highest-priority operator action blocking pipeline progress. */
export function resolvePendingAction(
  run: RunData | null,
  grants: Record<string, boolean> = {},
): PendingAction | null {
  if (!run) return null;

  const job = run.job;
  const ctx = resolveJobStatusContext(run, false);
  const focusStageId = findPendingFocusStage(run, grants);

  const actionStage = run.stages.find((s) => s.status === "action_required");
  if (actionStage) {
    return {
      kind: "gate",
      stageId: actionStage.id,
      stageTitle: actionStage.title,
      title: `${actionStage.title} needs your input`,
      message: "Complete the required steps in the checkpoint panel to continue.",
      primaryLabel: "Open checkpoint",
    };
  }

  if (job?.status === "gate" && job.stage) {
    const stage = run.stages.find((s) => s.id === job.stage);
    return {
      kind: "gate",
      stageId: job.stage,
      stageTitle: stage?.title || job.stage,
      title: stage ? `${stage.title} needs your input` : "Checkpoint required",
      message: job.message || "Action required before the pipeline can continue.",
      primaryLabel: "Open checkpoint",
    };
  }

  if (ctx.needsStageReuse && job?.stage) {
    const stage = run.stages.find((s) => s.id === job.stage);
    return {
      kind: "stage_reuse",
      stageId: job.stage,
      stageTitle: stage?.title || job.stage,
      title: stage ? `${stage.title} — reuse prior outputs?` : "Reuse from prior run?",
      message:
        job.message ||
        "Pick a previous execution with the same source audio, or run this step fresh.",
      primaryLabel: "Choose reuse or run fresh",
    };
  }

  if (ctx.awaitingWriteApproval) {
    const sid = job?.pending_write_stage || job?.stage || focusStageId || "";
    const stage = sid ? run.stages.find((s) => s.id === sid) : null;
    const fileCount = parseFileCountFromMessage(job?.message);
    return {
      kind: "write_approval",
      stageId: sid,
      stageTitle: stage?.title || sid.replace(/_/g, " ") || "Stage",
      title: fileCount
        ? `Review ${fileCount} file${fileCount === 1 ? "" : "s"} before saving`
        : "Review outputs before saving",
      message:
        job?.message ||
        `${stage?.title || "This step"} produced outputs that need your approval before writing to disk.`,
      primaryLabel: fileCount
        ? `Review ${fileCount} file${fileCount === 1 ? "" : "s"}`
        : "Review & approve outputs",
      fileCount,
    };
  }

  const handoff = findHandoffStage(run);
  if (handoff) {
    return {
      kind: "handoff",
      stageId: handoff.id,
      stageTitle: handoff.title,
      title: `${handoff.title} finished — review AI outputs`,
      message: "Check the generated content above, then acknowledge to continue.",
      primaryLabel: "Acknowledge & continue",
    };
  }

  const blocking = run.journey?.blocking ?? run.blocking;
  if (blocking?.blocked && blocking.stage_id) {
    const stage = run.stages.find((s) => s.id === blocking.stage_id);
    return {
      kind: "blocked",
      stageId: blocking.stage_id,
      stageTitle: stage?.title || blocking.stage_id,
      title: "Pipeline blocked",
      message: blocking.message || "Complete the required step to continue.",
      primaryLabel: "Open checkpoint",
    };
  }

  return null;
}

export function stageNeedsPendingAction(
  run: RunData | null,
  stageId: string,
  grants: Record<string, boolean> = {},
): boolean {
  const pending = resolvePendingAction(run, grants);
  return Boolean(pending && pending.stageId === stageId);
}
