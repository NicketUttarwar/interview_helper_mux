import type { JourneyUiConfig, RunData, StageInfo } from "../types";
import { isPipelineAutopilotEnabled } from "./pipelineAutopilot";
import { autopilotHidesReviewGate } from "./autopilotResolution";
import { gateOperatorMustAct } from "./operatorGates";

export type ReviewGateKind =
  | "transcript_review"
  | "llm_gate"
  | "sfx_prompt"
  | "g1_vo"
  | "vo_contract"
  | "vo_coverage"
  | "write_approval";

export interface ReviewGateSpec {
  kind: ReviewGateKind;
  pathCount?: number;
  missingCount?: number;
}

function sfxPromptReviewPending(stage: StageInfo): boolean {
  const steps = stage.guidance?.steps ?? [];
  return steps.some((s) => s.id === "prompt_review" && s.status === "todo");
}

/** Map structured blocking.reason / job.gate → banner kind (G-01 / GUI-BANNER-01). */
export function reviewGateKindFromStructured(
  reasonOrGate: string | null | undefined,
  stageId?: string | null,
): ReviewGateKind | null {
  const raw = String(reasonOrGate || "")
    .trim()
    .toLowerCase();
  if (!raw) return null;
  if (raw === "transcript_review" || raw === "g0") return "transcript_review";
  if (raw === "g1_vo_pickup" || raw === "g1_vo" || raw === "g1_5_preview_pickup") {
    return "g1_vo";
  }
  if (raw === "vo_contract" || raw === "vo_contract_gate") return "vo_contract";
  if (raw === "vo_coverage" || raw === "vo_coverage_gate") return "vo_coverage";
  if (raw === "write_approval" || raw === "write-approval") return "write_approval";
  if (raw === "sfx_prompt" || raw === "sfx_prompt_craft") return "sfx_prompt";
  if (raw === "llm_gate" || raw === "gate") {
    if (stageId === "transcript_review") return "transcript_review";
    if (stageId === "g1_vo_pickup" || stageId === "g1_5_preview_pickup") return "g1_vo";
    return "llm_gate";
  }
  return null;
}

/** Whether this stage needs a sticky approve banner at the top of the workbench. */
export function resolveReviewGateSpec(
  run: RunData | null,
  stage: StageInfo | null,
  showDoneShell: boolean,
  config?: JourneyUiConfig | null,
): ReviewGateSpec | null {
  if (!run || !stage || showDoneShell) return null;

  const jobWaitingGate = run.job?.status === "gate";
  // G-01: autopilot may auto-act but must never hide a waiting gate.
  if (
    !jobWaitingGate &&
    isPipelineAutopilotEnabled(config) &&
    autopilotHidesReviewGate(run, stage.id, config)
  ) {
    return null;
  }

  if (stage.id === "transcript_review" && stage.status === "action_required") {
    return { kind: "transcript_review" };
  }

  const blocking = run.journey?.blocking ?? run.blocking;
  const structured =
    reviewGateKindFromStructured(blocking?.reason, blocking?.stage_id || stage.id) ||
    reviewGateKindFromStructured(run.job?.gate, run.job?.stage || stage.id);

  const gateAtStage =
    (blocking?.blocked &&
      (blocking.stage_id === stage.id || !blocking.stage_id) &&
      Boolean(blocking.reason)) ||
    (jobWaitingGate &&
      (run.job?.stage === stage.id || run.job?.current_stage === stage.id) &&
      stage.id !== "transcript_review");

  if (gateAtStage || (jobWaitingGate && run.job?.stage === stage.id)) {
    if (structured) {
      if (structured === "g1_vo") {
        return {
          kind: "g1_vo",
          missingCount:
            stage.id === "g1_5_preview_pickup"
              ? (run.g1_5_preview_pickup_pending?.length ?? 0)
              : (run.g1_missing?.length ?? 0),
        };
      }
      if (structured === "write_approval") {
        return { kind: "llm_gate" };
      }
      return { kind: structured };
    }
    if (stage.id === "transcript_review") {
      return { kind: "transcript_review" };
    }
    return { kind: "llm_gate" };
  }

  if (stage.status !== "action_required" && stage.status !== "automation_pending") return null;

  switch (stage.id) {
    case "transcript_review":
      return { kind: "transcript_review" };
    case "g1_vo_pickup":
      if (!gateOperatorMustAct(run, "g1_vo_pickup")) return null;
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
