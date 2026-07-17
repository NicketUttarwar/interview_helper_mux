import type { RunData, RunMeta, StageInfo } from "../types";

/** True when backend omits this stage from the operator step list. */
export function isStageHidden(stage: StageInfo): boolean {
  return stage.stage_visibility === "hidden";
}

/** Stages shown in sidebar numbering and navigation. */
export function visibleStages(stages: StageInfo[]): StageInfo[] {
  return stages.filter((s) => !isStageHidden(s));
}

export function gapFillSkipped(run?: RunData | null, meta?: RunMeta | null): boolean {
  if (run?.gap_fill_mode === "skipped") return true;
  return meta?.gap_fill_mode === "skipped";
}
