import { useMemo } from "react";
import type { ReuseCandidate, RunData } from "../types";
import { resolveStageReuseCheck } from "../utils/stageReuseOffers";

export interface StageReuseOffersState {
  candidates: ReuseCandidate[];
  loading: boolean;
  currentHashShort: string | null;
  checked: boolean;
  visible: boolean;
  refresh: () => void;
}

export { stageReuseOffersJobKey } from "../utils/stageReuseOffers";

/** Derives reuse offers from run/job/journey payload — no separate API fetch. */
export function useStageReuseOffers(
  _runId: string | null,
  stageId: string,
  stageStatus: string,
  job?: {
    needs_stage_reuse?: boolean;
    stage?: string;
    reuse_candidates?: ReuseCandidate[];
  },
  _onError?: (message: string) => void,
  opts?: {
    skip?: boolean;
    hashShort?: string | null;
    run?: RunData | null;
    onRefresh?: () => void;
  },
): StageReuseOffersState {
  const check = useMemo(
    () => resolveStageReuseCheck(opts?.run ?? null, stageId, stageStatus, job),
    [
      opts?.run,
      stageId,
      stageStatus,
      job?.needs_stage_reuse,
      job?.stage,
      job?.reuse_candidates,
      opts?.run?.journey?.blocking,
      opts?.run?.blocking,
      opts?.run?.meta?.stage_reuse,
    ],
  );

  const skip = Boolean(opts?.skip);
  const candidates = skip ? [] : check.embeddedCandidates;
  const visible = !skip && check.enabled && (check.blocking || candidates.length > 0);

  return {
    candidates,
    loading: false,
    currentHashShort: opts?.hashShort ?? null,
    checked: true,
    visible,
    refresh: () => opts?.onRefresh?.(),
  };
}
