import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../context/AppContext";
import { formatApiError } from "../utils/safeApi";

interface DisfluencyReviewState {
  ready?: boolean;
  pending_count?: number;
  stats?: { total?: number; pending?: number; confirmed?: number; rejected?: number };
  events?: { review_status: string }[];
}

export function useDisfluencyReviewGate(enabled: boolean) {
  const {
    run,
    completeDisfluencyReview,
    actionBusy,
    jobRunning,
    showToast,
    appendClientLog,
  } = useApp();
  const [loading, setLoading] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<DisfluencyReviewState | null>(null);

  const reload = useCallback(async () => {
    if (!enabled || !run) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api<DisfluencyReviewState>(`/api/runs/${run.run_id}/disfluency-review`);
      setState(data);
    } catch (reason) {
      const msg = formatApiError(reason, "Disfluency review");
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [enabled, run]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const pendingCount = state?.pending_count ?? 0;
  const totalCount = state?.stats?.total ?? state?.events?.length ?? 0;
  const reviewedCount = Math.max(0, totalCount - pendingCount);
  const busy = completing || actionBusy || jobRunning;

  const acceptAllAndProceed = useCallback(async () => {
    if (busy || !run) return;
    setCompleting(true);
    setError(null);
    try {
      await completeDisfluencyReview(true);
    } catch (reason) {
      const msg = formatApiError(reason, "Complete disfluency review");
      setError(msg);
      showToast(msg, "error");
      appendClientLog(msg, "error", "disfluency_review");
    } finally {
      setCompleting(false);
    }
  }, [busy, run, completeDisfluencyReview, showToast, appendClientLog]);

  const completeReview = useCallback(async () => {
    if (busy || !run) return;
    setCompleting(true);
    setError(null);
    try {
      await completeDisfluencyReview(false);
    } catch (reason) {
      const msg = formatApiError(reason, "Complete disfluency review");
      setError(msg);
      showToast(msg, "error");
      appendClientLog(msg, "error", "disfluency_review");
    } finally {
      setCompleting(false);
    }
  }, [busy, run, completeDisfluencyReview, showToast, appendClientLog]);

  return {
    loading,
    error,
    busy,
    pendingCount,
    reviewedCount,
    totalCount,
    ready: Boolean(state?.ready),
    acceptAllAndProceed,
    completeReview,
    reload,
  };
}
