import type { AppConfig, RunData, StageInfo, StageStep } from "../types";
import { listRequiredAttentionItems } from "./attentionQueue";
import { resolveReviewGateSpec, type ReviewGateSpec } from "./resolveReviewGate";

const STEP_PRIORITY = [
  "review_transcript",
  "prompt_review",
  "reuse",
  "run",
] as const;

function stepNeedsAction(step: StageStep): boolean {
  if (!step.primary_button) return false;
  if (step.status === "done" || step.status === "waiting") return false;
  return step.status === "todo" || step.status === "active" || step.status === "blocked";
}

/** Workbench substeps that expose a primary footer action for this parent stage. */
export function findActionableWorkbenchSteps(
  stage: StageInfo,
  _run: RunData | null,
): StageStep[] {
  const steps = stage.guidance?.steps ?? [];
  const actionable = steps.filter((s) => stepNeedsAction(s));
  return actionable.sort((a, b) => {
    const idx = (step: StageStep) => {
      const i = STEP_PRIORITY.indexOf(step.id as (typeof STEP_PRIORITY)[number]);
      return i >= 0 ? i : STEP_PRIORITY.length;
    };
    const ar = idx(a);
    const br = idx(b);
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
