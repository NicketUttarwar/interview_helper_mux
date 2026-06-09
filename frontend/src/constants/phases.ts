/** Human labels for operator journey phases (shared across pipeline nav and guidance). */
export const PHASE_LABELS: Record<string, string> = {
  start: "Start",
  prepare: "Prepare",
  understand: "Analyze",
  complete: "Complete",
  create: "Build",
  polish: "Sound",
  ship: "Export",
  analysis: "Analyze",
  flow1: "Build",
  flow2: "Build",
  flow3: "Export",
  gate: "Checkpoint",
};

export function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] || phase;
}
