import { parseLogDetail } from "./index";

export function findLatestHandoffAudit(
  stageId: string,
  entries?: Array<{ stage?: string; detail?: unknown }>,
): string | null {
  if (!entries?.length) return null;
  for (let i = entries.length - 1; i >= 0; i--) {
    const e = entries[i];
    if (e.stage !== stageId) continue;
    const d = parseLogDetail(e.detail);
    if (typeof d?.audit_path === "string") return d.audit_path;
  }
  return null;
}
