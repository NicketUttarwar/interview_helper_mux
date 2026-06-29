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

export function logRecoveryCommand(detail: LogEntry["detail"]): string | null {
  const obj = typeof detail === "object" && detail ? detail : parseLogDetail(detail);
  if (obj && typeof obj.recovery_command === "string" && obj.recovery_command.trim()) {
    return obj.recovery_command.trim();
  }
  return null;
}

export function shouldAutoExpandLogDetail(
  detail: LogEntry["detail"],
  level?: string,
): boolean {
  if (level === "error") return true;
  if (logRecoveryCommand(detail)) return true;
  return false;
}

export function stageTitleById(
  stages: { id: string; title: string }[] | undefined,
  stageId: string | undefined | null,
): string | null {
  if (!stageId || !stages) return null;
  return stages.find((s) => s.id === stageId)?.title ?? stageId;
}
