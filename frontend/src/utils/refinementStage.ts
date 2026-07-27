import type { RunData, StageInfo } from "../types";

/** Pass 2 badge: stage explicitly flagged, or id matches a known refinement/recompose pattern. */
export function isRefinementPassStage(stage: StageInfo): boolean {
  return Boolean(
    stage.refinement_pass ||
      stage.id.includes("_refine") ||
      stage.id.includes("gap_framing_recompose") ||
      stage.id.includes("refinement_agenda"),
  );
}

/** True once this run has any Refinement Pass signal worth surfacing in the GUI. */
export function runHasRefinementSignal(run: RunData | null | undefined): boolean {
  if (!run) return false;
  if (run.refinement_agenda) return true;
  if (run.listener_outcome_trajectory?.points?.length) return true;
  if (run.refinement_plan?.passes?.length) return true;
  if (run.refinement_champion && Object.keys(run.refinement_champion).length) return true;
  if (run.refinement_evidence_packets?.length) return true;
  if (run.refinement_cascade) return true;
  return run.stages.some(isRefinementPassStage);
}
