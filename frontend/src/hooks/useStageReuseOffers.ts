import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ReuseCandidate } from "../types";
import { formatApiError } from "../utils/safeApi";

export interface StageReuseOffersState {
  candidates: ReuseCandidate[];
  loading: boolean;
  currentHashShort: string | null;
  refresh: () => void;
}

export function useStageReuseOffers(
  runId: string | null,
  stageId: string,
  stageStatus: string,
  job?: {
    needs_stage_reuse?: boolean;
    stage?: string;
    reuse_candidates?: ReuseCandidate[];
  },
  onError?: (message: string) => void,
): StageReuseOffersState {
  const [candidates, setCandidates] = useState<ReuseCandidate[]>([]);
  const [currentHashShort, setCurrentHashShort] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(() => {
    if (!runId || stageStatus === "done") {
      setCandidates([]);
      setCurrentHashShort(null);
      return;
    }
    if (job?.needs_stage_reuse && job.stage === stageId && job.reuse_candidates?.length) {
      setCandidates(job.reuse_candidates);
      void api<{ current_source_audio_hash_short?: string | null }>(
        `/api/runs/${runId}/stages/${stageId}/reuse-offers`,
      )
        .then((offers) => {
          setCurrentHashShort(offers.current_source_audio_hash_short ?? null);
        })
        .catch((reason) => {
          onError?.(formatApiError(reason, "Reuse offers"));
        });
      setLoading(false);
      return;
    }
    setLoading(true);
    void api<{
      eligible?: boolean;
      candidates?: ReuseCandidate[];
      pending_decision?: { action?: string } | null;
      current_source_audio_hash_short?: string | null;
    }>(`/api/runs/${runId}/stages/${stageId}/reuse-offers`)
      .then((offers) => {
        setCurrentHashShort(offers.current_source_audio_hash_short ?? null);
        if (offers.eligible && !offers.pending_decision) {
          setCandidates(offers.candidates || []);
        } else {
          setCandidates([]);
        }
      })
      .catch((reason) => {
        setCandidates([]);
        onError?.(formatApiError(reason, "Reuse offers"));
      })
      .finally(() => setLoading(false));
  }, [runId, stageId, stageStatus, job?.needs_stage_reuse, job?.stage, job?.reuse_candidates, onError]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { candidates, loading, currentHashShort, refresh };
}
