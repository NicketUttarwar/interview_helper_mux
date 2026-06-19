import type { OperatorPhase, PhaseProgressSummary, RunData } from "../types";
import { PHASE_LABELS } from "../constants/phases";
import { WORKFLOW_STEPS } from "./workflowSteps";
import { resolvePipelineNav } from "./pipelineNavigation";
import { buildStageProgress, type BuildSubstepsOpts } from "./stageSubsteps";

const TODO_SUBSTEP_CAP = 5;

function stagePhase(stage: { operator_phase?: string; phase?: string }): OperatorPhase {
  const op = stage.operator_phase ?? stage.phase ?? "understand";
  if (op === "gate") return "complete";
  return op as OperatorPhase;
}

export function buildPhaseSubsteps(
  run: RunData,
  phase: OperatorPhase,
  opts: BuildSubstepsOpts & { selectedStageId?: string | null } = {},
): PhaseProgressSummary {
  const phaseGuidance = run.journey?.phase_guidance?.[phase];
  const goal =
    phaseGuidance?.goal ||
    WORKFLOW_STEPS.find((s) => s.id === phase)?.tooltip ||
    PHASE_LABELS[phase] ||
    "";

  const phaseStages = run.stages.filter((s) => stagePhase(s) === phase);
  const progress = run.journey?.phase_progress?.[phase];
  const stagesDone = progress?.done ?? phaseStages.filter((s) => s.status === "done").length;
  const stagesTotal = progress?.total ?? phaseStages.length;

  const todoSubsteps: PhaseProgressSummary["todoSubsteps"] = [];
  for (const stage of phaseStages) {
    const sp = buildStageProgress(stage, run, opts);
    for (const sub of sp.substeps) {
      if (sub.status === "todo" || sub.status === "running") {
        todoSubsteps.push(sub);
        if (todoSubsteps.length >= TODO_SUBSTEP_CAP) break;
      }
    }
    if (todoSubsteps.length >= TODO_SUBSTEP_CAP) break;
  }

  const nav = resolvePipelineNav(run, {
    selectedStageId: opts.selectedStageId ?? null,
    jobRunning: opts.jobRunning ?? false,
    apiGrants: opts.apiGrants ?? {},
  });

  let activeStageId: string | null = null;
  if (opts.jobRunning && run.job) {
    activeStageId = run.job.current_stage || run.job.stage || null;
  }
  if (!activeStageId) {
    activeStageId = nav.focusStageId ?? nav.currentStage?.id ?? null;
  }

  return {
    phase,
    goal,
    stagesDone,
    stagesTotal,
    todoSubsteps,
    activeStageId,
  };
}

export function isPhaseFullyComplete(run: RunData, phase: OperatorPhase): boolean {
  const phaseStages = run.stages.filter((s) => stagePhase(s) === phase);
  if (phaseStages.length === 0) return false;
  return phaseStages.every((s) => s.status === "done");
}
