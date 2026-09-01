import type { RunData, StageStep } from "../types";
import { isJobActivelyRunning } from "./jobStatus";
import { isAutoNavConsumed, markAutoNavConsumed } from "./autoNavigationLedger";
import { isStageHidden } from "./stageVisibility";

/** Gate / blocker stage id → default workbench step when operator must act. */
const GATE_FOCUS_STEP: Record<string, string> = {
  transcript_review: "review_transcript",
  g1_vo_pickup: "record_lines",
  g1_5_preview_pickup: "continue_sfx",
};

export interface FocusStepOpts {
  substepId?: string | null;
  blockingReason?: string | null;
  blockingStageId?: string | null;
}

function stageSteps(run: RunData | null, stageId: string | null): StageStep[] {
  if (!run || !stageId) return [];
  const stage = run.stages.find((s) => s.id === stageId);
  return stage?.guidance?.steps ?? [];
}

function hasStep(steps: StageStep[], stepId: string): boolean {
  return steps.some((s) => s.id === stepId);
}

export function journeySubstepForStage(
  activeSubstepId: string | null | undefined,
  stageId: string,
): string | null {
  if (!activeSubstepId) return null;
  const colon = activeSubstepId.indexOf(":");
  if (colon < 0) return activeSubstepId;
  const scopedStageId = activeSubstepId.slice(colon + 1);
  return scopedStageId === stageId ? activeSubstepId : null;
}

const GATE_STAGE_TO_STEP: Record<string, string> = {
  transcript_review: "review_transcript",
};

/** Map journey substep ids to workbench step ids. */
export function substepIdToStepId(substepId: string | null | undefined): string | null {
  if (!substepId) return null;
  if (substepId.startsWith("stage_reuse")) return "reuse";
  if (substepId.startsWith("run:")) return "run";
  if (substepId.startsWith("blocked:")) {
    const bare = substepId.split(":").pop();
    return bare || null;
  }
  if (substepId.startsWith("gate:")) {
    const stageId = substepId.slice("gate:".length);
    return GATE_STAGE_TO_STEP[stageId] ?? stageId;
  }
  if (substepId.includes(":")) {
    const bare = substepId.split(":").pop();
    if (bare && GATE_STAGE_TO_STEP[bare]) return GATE_STAGE_TO_STEP[bare];
    return bare || null;
  }
  return substepId;
}

/** First actionable workbench step for a stage given current run state. */
export function resolveFocusStepId(
  run: RunData | null,
  stageId: string | null,
  opts: FocusStepOpts = {},
): string | null {
  if (!stageId) return null;
  const stage = run?.stages.find((s) => s.id === stageId);
  if (stage && isStageHidden(stage)) return null;
  const steps = stageSteps(run, stageId);
  const job = run?.job;
  const blocking = run?.journey?.blocking ?? run?.blocking;
  const blockingReason =
    opts.blockingReason ?? (blocking?.stage_id === stageId ? blocking.reason : null);
  const substepHint =
    opts.substepId ?? journeySubstepForStage(run?.journey?.active_substep_id, stageId);

  const fromSubstep = substepIdToStepId(substepHint);
  if (fromSubstep && (steps.length === 0 || hasStep(steps, fromSubstep))) return fromSubstep;

  if (stageId === "transcript_review") {
    const gateStep = GATE_FOCUS_STEP.transcript_review;
    if (hasStep(steps, gateStep)) return gateStep;
  }

  if (
    blockingReason === "llm_gate" ||
    (job?.status === "gate" && job.stage === stageId && stageId !== "transcript_review")
  ) {
    if (hasStep(steps, "llm_gate")) return "llm_gate";
    return "llm_gate";
  }

  if (
    blockingReason === "stage_reuse" ||
    (job?.needs_stage_reuse && (job.stage === stageId || job.current_stage === stageId))
  ) {
    if (hasStep(steps, "reuse")) return "reuse";
    if (blockingReason === "stage_reuse" || job?.needs_stage_reuse) return "reuse";
  }

  if (!steps.length) return null;

  const jobStage = job?.current_stage || job?.stage;
  if (jobStage === stageId && isJobActivelyRunning(job)) {
    const activeRun = steps.find((s) => s.kind === "run" && s.status === "active");
    if (activeRun) return activeRun.id;
    if (hasStep(steps, "wait_run")) return "wait_run";
    if (hasStep(steps, "run")) return "run";
  }

  if (stage?.status === "action_required" && GATE_FOCUS_STEP[stageId]) {
    const gateStep = GATE_FOCUS_STEP[stageId];
    if (hasStep(steps, gateStep)) return gateStep;
  }

  if (blockingReason && GATE_FOCUS_STEP[blockingReason]) {
    const gateStep = GATE_FOCUS_STEP[blockingReason];
    if (hasStep(steps, gateStep)) return gateStep;
  }

  return firstTodoStepId(run, stageId);
}

export function resolveActiveStep(
  run: RunData | null,
  stageId: string | null,
  activeStepId: string | null,
): StageStep | null {
  if (!run || !stageId) return null;
  const steps = stageSteps(run, stageId);
  if (!steps.length) return null;

  if (activeStepId) {
    const explicit = steps.find((s) => s.id === activeStepId);
    if (explicit) return explicit;
  }

  const focusId = resolveFocusStepId(run, stageId);
  if (focusId) {
    const focused = steps.find((s) => s.id === focusId);
    if (focused) return focused;
  }

  const fallbackId = firstTodoStepId(run, stageId);
  if (fallbackId) {
    const fallback = steps.find((s) => s.id === fallbackId);
    if (fallback) return fallback;
  }
  return steps[0] ?? null;
}

export function firstTodoStepId(run: RunData | null, stageId: string | null): string | null {
  if (!run || !stageId) return null;
  const steps = stageSteps(run, stageId);
  if (!steps.length) return null;
  const actionable = steps.find(
    (s) => s.status === "todo" || s.status === "active" || s.status === "blocked",
  );
  return actionable?.id ?? steps[0]?.id ?? null;
}

export interface AdvanceStaleStepOpts {
  userReviewingCompletedStep?: boolean;
}

export function shouldAdvanceStaleStep(
  run: RunData | null,
  stageId: string | null,
  activeStepId: string | null,
  opts: AdvanceStaleStepOpts = {},
): string | null {
  if (!run || !stageId || !activeStepId) return null;
  const steps = stageSteps(run, stageId);
  const current = steps.find((s) => s.id === activeStepId);
  if (!current) return resolveFocusStepId(run, stageId);
  if (current.status !== "done" && current.status !== "waiting") return null;
  if (opts.userReviewingCompletedStep) return null;
  const next = resolveFocusStepId(run, stageId);
  if (!next || next === activeStepId) return null;
  const target = { stageId, stepId: next };
  if (isAutoNavConsumed(target)) return null;
  markAutoNavConsumed(target);
  return next;
}
