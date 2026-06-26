import { useCallback, useEffect, useState } from "react";
import { useApp } from "../context/AppContext";
import { formatApiError } from "../utils/safeApi";

export function useTranscriptReviewGate(enabled: boolean) {
  const {
    run,
    loadTranscriptReview,
    transcriptReview,
    completeTranscriptReview,
    actionBusy,
    jobRunning,
    showToast,
    appendClientLog,
  } = useApp();
  const [loading, setLoading] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!enabled || !run) return;
    setLoading(true);
    setError(null);
    try {
      await loadTranscriptReview();
    } catch (reason) {
      const msg = formatApiError(reason, "Transcript review");
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [enabled, run, loadTranscriptReview]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const chunks = transcriptReview?.chunks ?? [];
  const pendingCount = transcriptReview?.pending_count ?? 0;
  const totalCount = chunks.length;
  const reviewedCount = Math.max(0, totalCount - pendingCount);
  const busy = completing || actionBusy || jobRunning;

  const acceptAllAndProceed = useCallback(async () => {
    if (busy || !run) return;
    setCompleting(true);
    setError(null);
    try {
      await completeTranscriptReview(true);
    } catch (reason) {
      const msg = formatApiError(reason, "Complete transcript review");
      setError(msg);
      showToast(msg, "error");
      appendClientLog(msg, "error", "transcript_review");
    } finally {
      setCompleting(false);
    }
  }, [busy, run, completeTranscriptReview, showToast, appendClientLog]);

  const completeReview = useCallback(async () => {
    if (busy || !run) return;
    setCompleting(true);
    setError(null);
    try {
      await completeTranscriptReview(false);
    } catch (reason) {
      const msg = formatApiError(reason, "Complete transcript review");
      setError(msg);
      showToast(msg, "error");
      appendClientLog(msg, "error", "transcript_review");
    } finally {
      setCompleting(false);
    }
  }, [busy, run, completeTranscriptReview, showToast, appendClientLog]);

  return {
    loading,
    error,
    busy,
    pendingCount,
    reviewedCount,
    totalCount,
    ready: Boolean(transcriptReview?.ready) && totalCount > 0,
    acceptAllAndProceed,
    completeReview,
    reload,
  };
}
