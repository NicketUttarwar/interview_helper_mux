import type { OperatorPhase, PipelineSubTab, RunData } from "../types";

export type WorkflowStepId = "start" | OperatorPhase;

export type WorkflowStepStatus = "done" | "active" | "upcoming";

export interface WorkflowStepDef {
  id: WorkflowStepId;
  label: string;
  tooltip: string;
  subTab: PipelineSubTab;
}

export const WORKFLOW_STEPS: WorkflowStepDef[] = [
  {
    id: "start",
    label: "Start",
    tooltip: "Pick source audio and choose your output type.",
    subTab: "stage",
  },
  {
    id: "prepare",
    label: "Prepare",
    tooltip: "Transcribe the interview and fix speech-to-text errors.",
    subTab: "stage",
  },
  {
    id: "understand",
    label: "Analyze",
    tooltip: "AI analyzes the interview. Review themes and story profile.",
    subTab: "story",
  },
  {
    id: "complete",
    label: "Complete",
    tooltip: "Record missing voice lines and confirm your output choice.",
    subTab: "stage",
  },
  {
    id: "create",
    label: "Build",
    tooltip: "Generate episode order, highlights, or show description.",
    subTab: "stage",
  },
  {
    id: "polish",
    label: "Sound",
    tooltip: "Add sound design and mix the final audio.",
    subTab: "stage",
  },
  {
    id: "ship",
    label: "Export",
    tooltip: "Download your master WAV or show description.",
    subTab: "stage",
  },
];

const PHASE_ORDER: OperatorPhase[] = [
  "prepare",
  "understand",
  "complete",
  "create",
  "polish",
  "ship",
];

export function currentWorkflowStep(run: RunData | null): WorkflowStepId {
  if (!run) return "start";
  return run.journey?.phase ?? run.meta?.operator_phase ?? "prepare";
}

export function workflowStepStatus(
  stepId: WorkflowStepId,
  run: RunData | null,
): WorkflowStepStatus {
  if (stepId === "start") {
    return run ? "done" : "active";
  }
  if (!run) return "upcoming";

  const phase = currentWorkflowStep(run);
  if (phase === "start") return "upcoming";

  const stepIdx = PHASE_ORDER.indexOf(stepId as OperatorPhase);
  const currentIdx = PHASE_ORDER.indexOf(phase);
  if (stepIdx < 0 || currentIdx < 0) return "upcoming";

  if (stepIdx < currentIdx) return "done";
  if (stepIdx > currentIdx) return "upcoming";

  const prog = run.journey?.phase_progress?.[stepId];
  if (prog && prog.total > 0 && prog.done >= prog.total) return "done";
  return "active";
}

export function workflowStepIndex(stepId: WorkflowStepId): number {
  return WORKFLOW_STEPS.findIndex((s) => s.id === stepId);
}

export function stageIdForStep(stepId: WorkflowStepId, run: RunData): string | null {
  if (stepId === "start") return null;

  const inPhase = run.stages.filter(
    (s) => (s.operator_phase ?? s.phase ?? "understand") === stepId,
  );
  const action = inPhase.find((s) => s.status === "action_required");
  if (action) return action.id;

  const pending = inPhase.find((s) => s.status === "pending");
  if (pending) return pending.id;

  const lastDone = [...inPhase].reverse().find((s) => s.status === "done");
  return lastDone?.id ?? inPhase[0]?.id ?? null;
}

export function stepNeedsCheckpoint(stepId: WorkflowStepId, run: RunData): boolean {
  if (stepId === "start") return false;
  const inPhase = run.stages.filter(
    (s) => (s.operator_phase ?? s.phase ?? "understand") === stepId,
  );
  return inPhase.some((s) => s.status === "action_required");
}
