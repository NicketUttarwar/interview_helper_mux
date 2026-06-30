import type { AppConfig, RunData, StageInfo } from "../types";
import { findLatestHandoffAudit } from "./handoff";
import { getHandoffPathsLocal } from "./checkpoint";
import { resolvePendingWritePaths, stageAwaitingWriteApproval } from "./writeApproval";
import { autopilotHidesReviewGate } from "./autopilotResolution";
import { isPipelineAutopilotEnabled } from "./pipelineAutopilot";

export type ReviewGateKind =
  | "transcript_review"
  | "disfluency_review"
  | "analysis_profile"
  | "write_approval"
  | "artifact_clarification"
  | "llm_gate"
  | "handoff"
  | "sfx_prompt"
  | "flow_select"
  | "g1_vo";

export interface ReviewGateSpec {
  kind: ReviewGateKind;
  pathCount?: number;
  missingCount?: number;
}

function handoffPending(run: RunData, stage: StageInfo): boolean {
  if (stage.status !== "done") return false;
  if (run.handoff_ack?.[stage.id]) return false;
  const paths = getHandoffPathsLocal(stage, run.log_tail);
  const audit = findLatestHandoffAudit(stage.id, run.log_tail);
  return (
    paths.length > 0 ||
    Boolean(audit) ||
    (run.journey?.blocking?.reason === "handoff_review" &&
      run.journey?.blocking?.stage_id === stage.id)
  );
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
  config?: AppConfig | null,
): ReviewGateSpec | null {
  if (!run || !stage || showDoneShell) return null;

  if (isPipelineAutopilotEnabled(config) && autopilotHidesReviewGate(run, stage.id, config)) {
    return null;
  }

  if (stageAwaitingWriteApproval(run, stage.id)) {
    const paths = resolvePendingWritePaths(run, stage.id);
    return { kind: "write_approval", pathCount: paths.length };
  }

  if (
    run.journey?.blocking?.reason === "artifact_clarification" &&
    run.journey?.blocking?.stage_id === stage.id
  ) {
    const open = run.job?.itr_blocking_count ?? 0;
    return { kind: "artifact_clarification", pathCount: open };
  }

  if (run.job?.status === "needs_clarification" && run.job?.stage === stage.id) {
    return {
      kind: "artifact_clarification",
      pathCount: Number(run.job?.itr_blocking_count ?? 0),
    };
  }

  if (
    (run.journey?.blocking?.reason === "llm_gate" &&
      run.journey?.blocking?.stage_id === stage.id) ||
    (run.job?.status === "gate" && run.job?.stage === stage.id)
  ) {
    return { kind: "llm_gate" };
  }

  if (handoffPending(run, stage)) {
    const paths = getHandoffPathsLocal(stage, run.log_tail);
    return { kind: "handoff", pathCount: paths.length };
  }

  if (stage.status !== "action_required") return null;

  switch (stage.id) {
    case "transcript_review":
      return { kind: "transcript_review" };
    case "disfluency_review":
      return { kind: "disfluency_review" };
    case "analysis_profile":
      return { kind: "analysis_profile" };
    case "g2_flow_select":
      return { kind: "flow_select" };
    case "g1_vo_pickup":
      return { kind: "g1_vo", missingCount: run.g1_missing?.length ?? 0 };
    case "sfx_prompt_craft":
      return sfxPromptReviewPending(stage) ? { kind: "sfx_prompt" } : null;
    default:
      return null;
  }
}
