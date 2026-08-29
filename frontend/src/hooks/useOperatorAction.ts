import { useMemo } from "react";
import type { RunData } from "../types";
import type { OperatorAction, OperatorActionContext } from "../types/operatorAction";
import {
  resolveOperatorAction,
  resolveOperatorActionForStage,
} from "../utils/resolveOperatorAction";

export function useGlobalOperatorAction(
  run: RunData | null,
  ctx: OperatorActionContext,
): OperatorAction {
  return useMemo(
    () => resolveOperatorAction(run, ctx),
    [
      run,
      ctx.selectedStageId,
      ctx.jobRunning,
      ctx.apiGrants,
      ctx.preferStageId,
      ctx.gPublish,
      run?.job,
      run?.journey,
    ],
  );
}

export function useStageOperatorAction(
  run: RunData | null,
  stageId: string | null,
  ctx: OperatorActionContext,
): OperatorAction | null {
  return useMemo(() => {
    if (!run || !stageId) return null;
    return resolveOperatorActionForStage(run, stageId, ctx);
  }, [
    run,
    stageId,
    ctx.selectedStageId,
    ctx.jobRunning,
    ctx.apiGrants,
    ctx.gPublish,
    run?.job,
    run?.journey,
  ]);
}
