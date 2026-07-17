import type { OperatorPhase, PipelineSubTab, RunData } from "../types";
import {
  attentionCountForPhase,
  phaseAttentionStatus as computePhaseAttentionStatus,
  phaseHasBlockingAttention,
} from "./attentionQueue";

export type WorkflowStepId = "start" | OperatorPhase;

export type WorkflowStepStatus = "done" | "active" | "upcoming" | "attention";

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
    label: "Record & choose",
    tooltip: "Record missing voice lines before delivery (G1).",
    subTab: "stage",
  },
  {
    id: "create",
    label: "Build",
    tooltip: "Generate episode order and assembly preview.",
    subTab: "stage",
  },
  {
    id: "polish",
    label: "Sound",
    tooltip: "Add SFX, review under-speech blend, and mix the final audio.",
    subTab: "stage",
  },
  {
    id: "ship",
    label: "Export",
    tooltip: "Download your master WAV or show description.",
    subTab: "stage",
  },
];

export function workflowStepsForRun(run: RunData | null): WorkflowStepDef[] {
  const skipped =
    run?.gap_fill_mode === "skipped" || run?.meta?.gap_fill_mode === "skipped";
  if (!skipped) return WORKFLOW_STEPS;
  return WORKFLOW_STEPS.map((step) =>
    step.id === "complete"
      ? {
          ...step,
          label: "Choose flow",
          tooltip: "Pick your delivery flow after analysis completes (no VO pickup needed).",
        }
      : step,
  );
}

export function currentWorkflowStep(run: RunData | null): WorkflowStepId {
  if (!run) return "start";
  return run.journey?.phase ?? run.meta?.operator_phase ?? "prepare";
}

export function workflowStepStatus(
  stepId: WorkflowStepId,
  run: RunData | null,
  grants: Record<string, boolean> = {},
): WorkflowStepStatus {
  return computePhaseAttentionStatus(stepId, run, grants);
}

export function workflowStepAttentionCount(
  stepId: WorkflowStepId,
  run: RunData | null,
  grants: Record<string, boolean> = {},
): number {
  if (stepId === "start" || !run) return 0;
  return attentionCountForPhase(run, stepId as OperatorPhase, grants);
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

  const awaiting = inPhase.find((s) => s.status === "awaiting_write_approval");
  if (awaiting) return awaiting.id;

  const pending = inPhase.find((s) => s.status === "pending");
  if (pending) return pending.id;

  const lastDone = [...inPhase].reverse().find((s) => s.status === "done");
  return lastDone?.id ?? inPhase[0]?.id ?? null;
}

export function stepNeedsCheckpoint(
  stepId: WorkflowStepId,
  run: RunData,
  grants: Record<string, boolean> = {},
): boolean {
  return phaseHasBlockingAttention(run, stepId, grants);
}
