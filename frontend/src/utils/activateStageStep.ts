/** Scroll to a stage step in the workbench — no modals. */
export function scrollToStageStep(stepId: string): void {
  const el = document.getElementById(`stage-step-${stepId}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}
