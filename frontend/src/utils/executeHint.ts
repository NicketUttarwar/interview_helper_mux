import type { ExecuteBody, JourneyExecuteHint } from "../types";

export function hintToExecuteBody(hint: JourneyExecuteHint): ExecuteBody | null {
  if (hint.action === "checkpoint") return null;
  if (!hint.mode) return null;
  return {
    mode: hint.mode as ExecuteBody["mode"],
    from_stage: hint.from_stage,
    until_stage: hint.until_stage,
  };
}
