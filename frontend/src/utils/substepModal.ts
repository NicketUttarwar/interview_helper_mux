import type { StageSubstep } from "../types";

const MODAL_KINDS = new Set<StageSubstep["kind"]>([
  "write_approval",
  "handoff",
  "reuse",
  "gate",
  "blocked",
  "checkpoint",
]);

/** Substeps that should open the operator checkpoint modal when activated. */
export function substepShouldOpenModal(substep: StageSubstep): boolean {
  if (MODAL_KINDS.has(substep.kind)) return true;
  if (substep.kind === "optional" && substep.id !== "optional:skip") return true;
  return false;
}
