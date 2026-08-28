/** Gate focus parity with backend gate_focus.py */

import type { RunData } from "../types";

export function operatorGateFocusStage(
  message: string | undefined,
  jobStage?: string | null,
): string | null {
  if (!message) return null;
  const low = message.toLowerCase();
  if (low.includes("transcript review")) {
    return "transcript_review";
  }
  if (low.includes("framing posture") || low.includes("framing_posture_decide")) {
    return "framing_posture_decide";
  }
  if (low.includes("vo_line_adjudicate") || low.includes("vo adjudicate")) {
    return "vo_line_adjudicate";
  }
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
  if (!job) return null;
  const msg = job.message || job.error || "";
  const operator = operatorGateFocusStage(msg, job.stage);
  if (operator) return operator;
  if (!job.stage) return null;
  return upstreamStageFromGateMessage(msg, job.stage) || job.stage;
}
