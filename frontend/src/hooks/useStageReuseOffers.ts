import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
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

interface ReuseOffersPayload {
  eligible?: boolean;
  candidates?: ReuseCandidate[];
}

/** Embedded run/job candidates plus proactive reuse-offers API when browsing a stage. */
export function useStageReuseOffers(
  runId: string | null,
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

  const skip = Boolean(opts?.skip) || stageStatus === "done";
  const hasEmbedded = check.embeddedCandidates.length > 0;

  const [fetchedCandidates, setFetchedCandidates] = useState<ReuseCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [checked, setChecked] = useState(false);
  const [fetchGeneration, setFetchGeneration] = useState(0);

  useEffect(() => {
    if (skip || !runId) {
      setFetchedCandidates([]);
      setLoading(false);
      setChecked(true);
      return;
    }
    if (hasEmbedded) {
      setFetchedCandidates([]);
      setLoading(false);
      setChecked(true);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setChecked(false);
    void api<ReuseOffersPayload>(`/api/runs/${runId}/stages/${stageId}/reuse-offers`)
      .then((payload) => {
        if (cancelled) return;
        const list =
          payload.eligible && Array.isArray(payload.candidates) ? payload.candidates : [];
        setFetchedCandidates(list);
        setChecked(true);
      })
      .catch(() => {
        if (!cancelled) {
          setFetchedCandidates([]);
          setChecked(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [runId, stageId, skip, hasEmbedded, fetchGeneration]);

  const candidates = skip ? [] : hasEmbedded ? check.embeddedCandidates : fetchedCandidates;
  const visible =
    !skip && (candidates.length > 0 || check.enabled || (loading && !checked));

  const refresh = () => {
    if (hasEmbedded) {
      opts?.onRefresh?.();
      return;
    }
    setFetchGeneration((g) => g + 1);
    opts?.onRefresh?.();
  };

  return {
    candidates,
    loading: loading && !checked,
    currentHashShort: opts?.hashShort ?? null,
    checked: hasEmbedded || checked,
    visible,
    refresh,
  };
}
