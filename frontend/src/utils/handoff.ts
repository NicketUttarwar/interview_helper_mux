import type { StageInfo } from "../types";

export function getHandoffPaths(
  stage: StageInfo,
  logTail: Array<{ stage?: string; detail?: unknown }> | undefined,
): string[] {
  const fromLog = findLatestHandoffForStage(stage.id, logTail);
  if (fromLog?.length) return fromLog;
  return [...(stage.artifacts_present || []), ...(stage.artifacts || [])].filter(
    (p, i, arr) => Boolean(p) && !p.endsWith("/") && arr.indexOf(p) === i,
  );
}

export function findLatestHandoffForStage(
  stageId: string,
  entries?: Array<{ stage?: string; detail?: unknown }>,
): string[] | null {
  if (!entries?.length) return null;
  for (let i = entries.length - 1; i >= 0; i--) {
    const e = entries[i];
    if (e.stage !== stageId) continue;
    const d = parseDetail(e.detail);
    const handoff = d?.handoff;
    if (Array.isArray(handoff) && handoff.length) return handoff as string[];
  }
  return null;
}

export function findLatestHandoffAudit(
  stageId: string,
  entries?: Array<{ stage?: string; detail?: unknown }>,
): string | null {
  if (!entries?.length) return null;
  for (let i = entries.length - 1; i >= 0; i--) {
    const e = entries[i];
    if (e.stage !== stageId) continue;
    const d = parseDetail(e.detail);
    if (typeof d?.audit_path === "string") return d.audit_path;
  }
  return null;
}

function parseDetail(detail: unknown): Record<string, unknown> | null {
  if (!detail) return null;
  if (typeof detail === "object") return detail as Record<string, unknown>;
  if (typeof detail === "string") {
    try {
      return JSON.parse(detail) as Record<string, unknown>;
    } catch {
      return null;
    }
  }
  return null;
}
