import type { RunData } from "../types";
import { resolveJobStatusContext } from "./operatorStatus";

export interface PendingWriteInfo {
  stageId: string;
  paths: string[];
}

/** True when gui_job blocks this stage behind an LLM or operator gate. */
export function isStageGateBlocked(run: RunData | null, stageId: string): boolean {
  if (!run?.job || run.job.status !== "gate") return false;
  const gateStage = run.job.pending_write_stage || run.job.stage;
  if (!gateStage || gateStage !== stageId) return false;
  const stage = run.stages.find((s) => s.id === stageId);
  return stage?.status !== "done";
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
