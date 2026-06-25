import type { RunData, StageStep } from "../types";

export function resolveActiveStep(
  run: RunData | null,
  stageId: string | null,
  activeStepId: string | null,
): StageStep | null {
  if (!run || !stageId) return null;
  const stage = run.stages.find((s) => s.id === stageId);
  const steps = stage?.guidance?.steps;
  if (!steps?.length) return null;

  if (activeStepId) {
    const explicit = steps.find((s) => s.id === activeStepId);
    if (explicit) return explicit;
  }

  const running = steps.find((s) => s.status === "active");
  if (running) return running;

  const todo = steps.find((s) => s.status === "todo");
  if (todo) return todo;

  const blocked = steps.find((s) => s.status === "blocked");
  if (blocked) return blocked;

  return steps[steps.length - 1] ?? null;
}

export function firstTodoStepId(run: RunData | null, stageId: string | null): string | null {
  if (!run || !stageId) return null;
  const stage = run.stages.find((s) => s.id === stageId);
  const steps = stage?.guidance?.steps;
  if (!steps?.length) return null;
  const todo = steps.find((s) => s.status === "todo" || s.status === "active" || s.status === "blocked");
  return todo?.id ?? steps[0]?.id ?? null;
}
