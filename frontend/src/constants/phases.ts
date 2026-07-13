/** Human labels for operator journey phases (shared across pipeline nav and guidance). */
export const PHASE_LABELS: Record<string, string> = {
  start: "Start",
  prepare: "Prepare",
  understand: "Analyze",
  complete: "Record pickup",
  create: "Build",
  polish: "Sound",
  ship: "Export",
  analysis: "Analyze",
  delivery: "Build",
  gate: "Checkpoint",
};

export function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] || phase;
}
