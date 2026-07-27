import type { RunData, RunMeta, StageInfo } from "../types";

/**
 * Steps panel always shows the full numbered list now (Refinement Pass
 * cleanup) — kept as a no-op for callers/tests that still reference it.
 */
export function isStageHidden(_stage: StageInfo): boolean {
  return false;
}

/** Stages shown in sidebar numbering and navigation. */
export function visibleStages(stages: StageInfo[]): StageInfo[] {
  return stages.filter((s) => !isStageHidden(s));
}

export function gapFillSkipped(run?: RunData | null, meta?: RunMeta | null): boolean {
  if (run?.gap_fill_mode === "skipped") return true;
  return meta?.gap_fill_mode === "skipped";
}
