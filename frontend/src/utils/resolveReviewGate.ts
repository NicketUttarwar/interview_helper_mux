import type { RunData, StageInfo } from "../types";
import { isPipelineAutopilotEnabled } from "./pipelineAutopilot";
import { autopilotHidesReviewGate } from "./autopilotResolution";

export type ReviewGateKind =
  | "transcript_review"
  | "llm_gate"
  | "sfx_prompt"
  | "g1_vo";

export interface ReviewGateSpec {
  kind: ReviewGateKind;
  pathCount?: number;
  missingCount?: number;
}

function sfxPromptReviewPending(stage: StageInfo): boolean {
  const steps = stage.guidance?.steps ?? [];
  return steps.some((s) => s.id === "prompt_review" && s.status === "todo");
}

/** Whether this stage needs a sticky approve banner at the top of the workbench. */
export function resolveReviewGateSpec(
  run: RunData | null,
  stage: StageInfo | null,
  showDoneShell: boolean,
  config?: { journey_ui?: { auto_advance_pipeline?: boolean } } | null,
): ReviewGateSpec | null {
  if (!run || !stage || showDoneShell) return null;

  if (isPipelineAutopilotEnabled(config) && autopilotHidesReviewGate(run, stage.id, config)) {
    return null;
  }

  if (
    (run.journey?.blocking?.reason === "llm_gate" &&
      run.journey?.blocking?.stage_id === stage.id) ||
    (run.job?.status === "gate" && run.job?.stage === stage.id)
  ) {
    return { kind: "llm_gate" };
  }

  if (stage.status !== "action_required") return null;

  switch (stage.id) {
    case "transcript_review":
      return { kind: "transcript_review" };
    case "g1_vo_pickup":
      return { kind: "g1_vo", missingCount: run.g1_missing?.length ?? 0 };
    case "g1_5_preview_pickup":
      return {
        kind: "g1_vo",
        missingCount: run.g1_5_preview_pickup_pending?.length ?? 0,
      };
    case "sfx_prompt_craft":
      return sfxPromptReviewPending(stage) ? { kind: "sfx_prompt" } : null;
    default:
      return null;
  }
}
