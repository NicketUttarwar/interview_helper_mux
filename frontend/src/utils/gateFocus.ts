/** Gate focus parity with backend gate_focus.py */

import type { RunData } from "../types";

export function operatorGateFocusStage(
  message: string | undefined,
  jobStage?: string | null,
): string | null {
  if (!message || !jobStage) return null;
  const low = message.toLowerCase();
  if (jobStage === "transcript_review_build" && low.includes("transcript review required")) {
    return "transcript_review";
  }
  return null;
}

export function upstreamStageFromGateMessage(
  message: string | undefined,
  currentStage?: string | null,
): string | null {
  if (!message) return null;
  const match = message.match(/(?:from stage|Prerequisite stage)\s+([a-z][a-z0-9_]*)/i);
  if (!match) return null;
  const upstream = match[1];
  if (currentStage && upstream === currentStage) return null;
  return upstream;
}

export function gateFocusStageId(job: RunData["job"]): string | null {
  if (!job?.stage) return null;
  const msg = job.message || job.error || "";
  return (
    upstreamStageFromGateMessage(msg, job.stage) ||
    operatorGateFocusStage(msg, job.stage) ||
    job.stage
  );
}
