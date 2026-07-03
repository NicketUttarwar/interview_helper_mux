import type { AppConfig, RunData, StageInfo, StageStep } from "../types";
import { listRequiredAttentionItems } from "./attentionQueue";
import { getHandoffPathsLocal } from "./checkpoint";
import { resolveReviewGateSpec, type ReviewGateSpec } from "./resolveReviewGate";
import { stageAwaitingWriteApproval } from "./writeApproval";

const STEP_PRIORITY = [
  "write_approval",
  "artifact_clarification",
  "operator_decisions",
  "handoff",
  "complete_g0",
  "review_fillers",
  "listen_clips",
  "complete_g05",
  "prompt_review",
  "verify_profile",
  "reuse",
  "run",
] as const;

function handoffStepPending(stage: StageInfo, run: RunData | null): boolean {
  if (!run || stage.status !== "done") return false;
  if (run.handoff_ack?.[stage.id]) return false;
  return getHandoffPathsLocal(stage, run.log_tail).length > 0;
}

function stepNeedsAction(step: StageStep, stage: StageInfo, run: RunData | null): boolean {
  if (!step.primary_button) return false;
  if (step.status === "done" || step.status === "waiting") return false;
  if (step.kind === "write_approval" || step.id === "write_approval") {
    return stageAwaitingWriteApproval(run, stage.id);
  }
  if (step.kind === "handoff" || step.id === "handoff") {
    return handoffStepPending(stage, run);
  }
  return step.status === "todo" || step.status === "active" || step.status === "blocked";
}

/** Workbench substeps that expose a primary footer action for this parent stage. */
export function findActionableWorkbenchSteps(
  stage: StageInfo,
  run: RunData | null,
): StageStep[] {
  const steps = stage.guidance?.steps ?? [];
  const actionable = steps.filter((s) => stepNeedsAction(s, stage, run));
  return actionable.sort((a, b) => {
    const ai = STEP_PRIORITY.indexOf(a.id as (typeof STEP_PRIORITY)[number]);
    const bi = STEP_PRIORITY.indexOf(b.id as (typeof STEP_PRIORITY)[number]);
    const ar = ai >= 0 ? ai : STEP_PRIORITY.length;
    const br = bi >= 0 ? bi : STEP_PRIORITY.length;
    if (ar !== br) return ar - br;
    return a.number - b.number;
  });
}

export interface StageWorkbenchProgress {
  reviewGateSpec: ReviewGateSpec | null;
  primaryStep: StageStep | null;
  secondaryStep: StageStep | null;
  attentionMessage: string | null;
  attentionLabel: string | null;
}

/** Resolve parent-stage progress banner content for the middle workbench panel. */
export function resolveStageWorkbenchProgress(
  run: RunData | null,
  stage: StageInfo | null,
  showDoneShell: boolean,
  config?: AppConfig | null,
): StageWorkbenchProgress | null {
  if (!run || !stage || showDoneShell) return null;

  const reviewGateSpec = resolveReviewGateSpec(run, stage, showDoneShell, config);
  const actionable = findActionableWorkbenchSteps(stage, run);
  const attention = listRequiredAttentionItems(run).filter((i) => i.stageId === stage.id);

  if (!reviewGateSpec && !actionable.length && !attention.length) {
    return null;
  }

  const primaryStep = actionable[0] ?? null;
  const secondaryStep =
    actionable.find((s) => s.id !== primaryStep?.id && s.secondary_button) ?? null;

  const topAttention = attention[0] ?? null;

  return {
    reviewGateSpec,
    primaryStep,
    secondaryStep,
    attentionMessage: topAttention?.message ?? primaryStep?.instruction ?? null,
    attentionLabel: topAttention?.primaryLabel ?? primaryStep?.primary_button ?? null,
  };
}
