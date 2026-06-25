import type { RunData, StageStep } from "../types";
import { isJobActivelyRunning } from "./jobStatus";
import { pendingWriteInfo, stageAwaitingWriteApproval } from "./writeApproval";

/** Gate / blocker stage id → default workbench step when operator must act. */
const GATE_FOCUS_STEP: Record<string, string> = {
  transcript_review: "listen_clips",
  disfluency_review: "review_fillers",
  analysis_profile: "review_profile",
  g1_vo_pickup: "review_lines",
  g2_flow_select: "choose_flow",
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

/** Map journey substep ids (write_approval:ingest) to workbench step ids. */
export function substepIdToStepId(substepId: string | null | undefined): string | null {
  if (!substepId) return null;
  if (substepId.startsWith("write_approval")) return "write_approval";
  if (substepId.startsWith("stage_reuse")) return "reuse";
  if (substepId.startsWith("handoff")) return "handoff";
  if (substepId.startsWith("run:")) return "run";
  if (substepId.startsWith("blocked:")) {
    const bare = substepId.split(":").pop();
    return bare || null;
  }
  if (substepId.includes(":")) {
    const bare = substepId.split(":").pop();
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
  const steps = stageSteps(run, stageId);
  const stage = run?.stages.find((s) => s.id === stageId);
  const job = run?.job;
  const blocking = run?.journey?.blocking ?? run?.blocking;
  const blockingReason =
    opts.blockingReason ?? (blocking?.stage_id === stageId ? blocking.reason : null);
  const substepHint =
    opts.substepId ??
    (blocking?.stage_id === stageId ? run?.journey?.active_substep_id : null) ??
    run?.journey?.active_substep_id;

  const fromSubstep = substepIdToStepId(substepHint);
  if (fromSubstep && (steps.length === 0 || hasStep(steps, fromSubstep))) return fromSubstep;

  const write = pendingWriteInfo(run);
  const awaitingWrite =
    write?.stageId === stageId ||
    stageAwaitingWriteApproval(run, stageId) ||
    blockingReason === "write_approval" ||
    stage?.status === "awaiting_write_approval";
  if (awaitingWrite) {
    if (hasStep(steps, "write_approval")) return "write_approval";
    if (write?.paths.length || stage?.status === "awaiting_write_approval") {
      return "write_approval";
    }
  }

  if (
    blockingReason === "stage_reuse" ||
    (job?.needs_stage_reuse && (job.stage === stageId || job.current_stage === stageId))
  ) {
    if (hasStep(steps, "reuse")) return "reuse";
    if (blockingReason === "stage_reuse" || job?.needs_stage_reuse) return "reuse";
  }

  if (blockingReason === "handoff_review") {
    if (hasStep(steps, "handoff")) return "handoff";
    return "handoff";
  }

  if (!steps.length) return null;

  const jobStage = job?.current_stage || job?.stage;
  if (
    jobStage === stageId &&
    isJobActivelyRunning(job) &&
    job?.mode !== "write_approval"
  ) {
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

  return steps[steps.length - 1] ?? null;
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

/** True when the operator should advance to a different step within the same stage. */
export function shouldAdvanceStaleStep(
  run: RunData | null,
  stageId: string | null,
  activeStepId: string | null,
): string | null {
  if (!run || !stageId || !activeStepId) return null;
  const steps = stageSteps(run, stageId);
  const current = steps.find((s) => s.id === activeStepId);
  if (!current) return resolveFocusStepId(run, stageId);
  if (current.status !== "done" && current.status !== "waiting") return null;
  const next = resolveFocusStepId(run, stageId);
  if (!next || next === activeStepId) return null;
  return next;
}
