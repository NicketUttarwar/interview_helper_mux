import { useMemo } from "react";
import type { RunData } from "../types";
import { resolveActiveStep } from "../utils/resolveActiveStep";

export function useActiveStageStep(
  run: RunData | null,
  stageId: string | null,
  activeStepId: string | null,
) {
  return useMemo(
    () => resolveActiveStep(run, stageId, activeStepId),
    [run, stageId, activeStepId],
  );
}
