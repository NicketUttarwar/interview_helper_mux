import { useMemo } from "react";
import { useApp } from "../context/AppContext";
import { buildStageProgress, findActiveSubstep } from "../utils/stageSubsteps";
import { buildPhaseSubsteps } from "../utils/phaseSubsteps";
import type { OperatorPhase } from "../types";

export function useStageProgress(stageId?: string | null) {
  const { run, jobRunning, actionBusy, apiGrants, selectedStageId } = useApp();

  const opts = useMemo(
    () => ({ jobRunning, actionBusy, apiGrants }),
    [jobRunning, actionBusy, apiGrants],
  );

  const stage = useMemo(() => {
    const sid = stageId ?? selectedStageId;
    if (!run || !sid) return null;
    return run.stages.find((s) => s.id === sid) ?? null;
  }, [run, stageId, selectedStageId]);

  const progress = useMemo(() => {
    if (!run || !stage) return null;
    return buildStageProgress(stage, run, opts);
  }, [run, stage, opts]);

  const activeSubstepGlobal = useMemo(() => {
    if (!run) return null;
    return findActiveSubstep(run, opts);
  }, [run, opts]);

  return {
    stage,
    progress,
    substeps: progress?.substeps ?? [],
    fullyComplete: progress?.fullyComplete ?? false,
    activeSubstep: progress?.activeSubstep ?? null,
    activeSubstepGlobal,
  };
}

export function usePhaseProgress(phase: OperatorPhase) {
  const { run, jobRunning, actionBusy, apiGrants, selectedStageId } = useApp();
  const opts = useMemo(
    () => ({ jobRunning, actionBusy, apiGrants, selectedStageId }),
    [jobRunning, actionBusy, apiGrants, selectedStageId],
  );

  return useMemo(() => {
    if (!run) return null;
    return buildPhaseSubsteps(run, phase, opts);
  }, [run, phase, opts]);
}
