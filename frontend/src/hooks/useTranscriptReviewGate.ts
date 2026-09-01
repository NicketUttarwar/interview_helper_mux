import { useCallback, useEffect, useState } from "react";
import { useApp } from "../context/AppContext";
import { guardBusy } from "../utils/guardBusy";
import { isPartialAutoCheckpoint } from "../utils/partialAcceleratedGuard";
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
    partialAutoGPublish,
  } = useApp();
  const atCheckpoint = isPartialAutoCheckpoint(run, partialAutoGPublish);
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
  const busy =
    completing || actionBusy || (jobRunning && !atCheckpoint);
  const busyReason =
    completing || actionBusy
      ? "Saving transcript edits…"
      : jobRunning && !atCheckpoint
        ? "Pipeline step still running — wait for the activity log."
        : null;

  const acceptAllAndProceed = useCallback(async () => {
    if (
      !atCheckpoint &&
      guardBusy(jobRunning, actionBusy || completing, showToast, { run, gPublish: partialAutoGPublish })
    ) {
      return;
    }
    if (!run) return;
    setCompleting(true);
    setError(null);
    try {
      await completeTranscriptReview(true);
    } catch (reason) {
      const msg = formatApiError(reason, "Complete transcript review");
      setError(msg);
      appendClientLog(msg, "error", "transcript_review");
    } finally {
      setCompleting(false);
    }
  }, [jobRunning, actionBusy, completing, run, partialAutoGPublish, completeTranscriptReview, showToast, appendClientLog, atCheckpoint]);

  const completeReview = useCallback(async () => {
    if (
      !atCheckpoint &&
      guardBusy(jobRunning, actionBusy || completing, showToast, { run, gPublish: partialAutoGPublish })
    ) {
      return;
    }
    if (!run) return;
    setCompleting(true);
    setError(null);
    try {
      await completeTranscriptReview(false);
    } catch (reason) {
      const msg = formatApiError(reason, "Complete transcript review");
      setError(msg);
      appendClientLog(msg, "error", "transcript_review");
    } finally {
      setCompleting(false);
    }
  }, [jobRunning, actionBusy, completing, run, partialAutoGPublish, completeTranscriptReview, showToast, appendClientLog, atCheckpoint]);

  return {
    loading,
    error,
    busy,
    pendingCount,
    reviewedCount,
    totalCount,
    ready: Boolean(transcriptReview?.ready),
    acceptAllAndProceed,
    completeReview,
    reload,
    busyReason,
  };
}
