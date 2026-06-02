import type { LogEntry } from "../types";
import { parseLogDetail } from "./index";

export function formatLogDetailBlock(
  detail?: LogEntry["detail"],
): { text: string; isJson: boolean } {
  if (!detail) return { text: "", isJson: false };
  if (typeof detail === "string") {
    const parsed = parseLogDetail(detail);
    if (parsed) {
      return { text: JSON.stringify(parsed, null, 2), isJson: true };
    }
    return { text: detail, isJson: false };
  }
  return { text: JSON.stringify(detail, null, 2), isJson: true };
}

export function logJourneyKind(detail: LogEntry["detail"]): string | null {
  const obj = typeof detail === "object" && detail ? detail : parseLogDetail(detail);
  if (obj && typeof obj.journey_kind === "string") return obj.journey_kind;
  return null;
}

export function stageTitleById(
  stages: { id: string; title: string }[] | undefined,
  stageId: string,
): string {
  return stages?.find((s) => s.id === stageId)?.title ?? stageId;
}
