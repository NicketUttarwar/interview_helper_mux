import { ApiError } from "../api/client";
import type { RunData } from "../types";
import { isWriteApprovalSaveInProgress } from "./jobStatus";
import { resolveJobStatusContext } from "./operatorStatus";

export interface PendingWriteInfo {
  stageId: string;
  paths: string[];
}

/** True when gui_job blocks this stage behind an LLM or operator gate. */
export function isStageGateBlocked(run: RunData | null, stageId: string): boolean {
  if (!run?.job || run.job.status !== "gate") return false;
  const gateStage = run.job.pending_write_stage || run.job.stage;
  return Boolean(gateStage && gateStage === stageId);
}

/** Resolve staged file paths from job state, run meta, or API response. */
export function resolvePendingWritePaths(
  run: RunData | null,
  stageId: string,
  apiPaths?: string[],
): string[] {
  if (!run || !stageId) return [];
  if (isStageGateBlocked(run, stageId)) return [];

  const awaiting = stageAwaitingWriteApproval(run, stageId);
  if (!awaiting) return [];

  if (apiPaths?.length) return apiPaths;

  const job = run.job;
  if (
    (job?.pending_write_stage === stageId || job?.stage === stageId) &&
    job.pending_write_paths?.length
  ) {
    return job.pending_write_paths;
  }

  const metaPending = run.meta?.pending_write_approval as
    | Record<string, { paths?: string[] }>
    | undefined;
  const fromMeta = metaPending?.[stageId]?.paths;
  if (fromMeta?.length) return fromMeta;

  return [];
}

export function pendingWriteInfo(run: RunData | null): PendingWriteInfo | null {
  if (!run) return null;
  const ctx = resolveJobStatusContext(run, false);
  if (!ctx.awaitingWriteApproval) return null;
  const stageId = run.job?.pending_write_stage || run.job?.stage;
  if (!stageId) return null;
  const paths = resolvePendingWritePaths(run, stageId);
  return { stageId, paths };
}

export function stageAwaitingWriteApproval(
  run: RunData | null,
  stageId: string,
): boolean {
  if (!run) return false;
  if (isStageGateBlocked(run, stageId)) return false;
  const stage = run.stages.find((s) => s.id === stageId);
  if (stage?.status === "awaiting_write_approval") return true;
  const ctx = resolveJobStatusContext(run, false);
  if (!ctx.awaitingWriteApproval) return false;
  const pendingStage = run.job?.pending_write_stage || run.job?.stage;
  return pendingStage === stageId;
}

/** True when the GUI should fetch staged file lists or content for this stage. */
export function canLoadPendingWriteContent(
  run: RunData | null,
  stageId: string,
  opts?: { actionBusy?: boolean; apiPaths?: string[] },
): boolean {
  if (!run || !stageId) return false;
  if (isWriteApprovalSaveInProgress(run, { actionBusy: opts?.actionBusy, stageId })) {
    return false;
  }
  if (!stageAwaitingWriteApproval(run, stageId)) return false;
  return resolvePendingWritePaths(run, stageId, opts?.apiPaths).length > 0;
}

/** 404 after staging was flushed or wrong stage — safe to ignore in write-approval UI. */
export function isStalePendingWriteLoadError(reason: unknown): boolean {
  if (!(reason instanceof ApiError) || reason.status !== 404) return false;
  const msg = reason.message;
  return (
    msg.includes(".pending_writes/") ||
    msg.includes("No pending writes for stage")
  );
}
