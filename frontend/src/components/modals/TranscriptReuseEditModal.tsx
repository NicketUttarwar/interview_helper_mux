import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { focusNextRunnableStageWorkbench } from "../../utils/stageAdvance";
import { guardBusy } from "../../utils/guardBusy";
import {
  formatCorrectionSummary,
  TranscriptDockViewer,
  type TranscriptCorrectionStats,
  type TranscriptDockHandle,
} from "../workspace/TranscriptDockViewer";
import { emptyCorrectionStats } from "../../utils/transcriptCorrectionStats";
import {
  markTranscriptReuseEditConsumed,
  shouldOpenTranscriptReuseEdit,
  syncTranscriptReuseEditConsumed,
  transcriptReuseEditPending,
} from "../../utils/transcriptReuseEditGate";

/**
 * One-time interstitial after accepting transcript reuse.
 * Uses the same synced dock + fuzzy similar-word tools as STT review.
 * Does not stay open just because the operator is later on the G0 stage.
 */
export function TranscriptReuseEditModal() {
  const {
    runId,
    run,
    transcriptReuseEditOpen,
    openTranscriptReuseEdit,
    closeTranscriptReuseEdit,
    refreshRun,
    showToast,
    advanceFromCheckpoint,
    autoContinuePipeline,
    selectStage,
    expandStage,
    setActiveStepId,
    setPipelineSubTab,
    jobRunning,
    actionBusy,
    setCheckpointBusy,
  } = useApp();

  const [saving, setSaving] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const [correctionStats, setCorrectionStats] = useState<TranscriptCorrectionStats>(
    emptyCorrectionStats(),
  );
  const [dockReady, setDockReady] = useState(false);
  const dockRef = useRef<TranscriptDockHandle>(null);

  const pending = transcriptReuseEditPending(run?.meta);
  const open = transcriptReuseEditOpen;

  // One-time interstitial: open only when server pending flag is set and not yet consumed.
  useEffect(() => {
    if (!runId) return;
    syncTranscriptReuseEditConsumed(runId, run?.meta);
    if (!shouldOpenTranscriptReuseEdit(runId, run?.meta)) {
      if (transcriptReuseEditOpen) closeTranscriptReuseEdit();
      return;
    }
    if (!transcriptReuseEditOpen) openTranscriptReuseEdit();
  }, [
    runId,
    run?.meta,
    pending,
    transcriptReuseEditOpen,
    openTranscriptReuseEdit,
    closeTranscriptReuseEdit,
  ]);

  useEffect(() => {
    setCorrectionStats(emptyCorrectionStats());
    setDockReady(false);
  }, [runId]);

  useEffect(() => {
    if (!open) return;
    setDockReady(true);
  }, [open]);

  if (!open) return null;

  const busy = saving || dismissing;

  const afterCloseContinue = async () => {
    const refreshed = (await refreshRun()) ?? run;
    if (!refreshed) return;
    const continued = await autoContinuePipeline("transcribe");
    if (continued) return;
    await advanceFromCheckpoint();
    await focusNextRunnableStageWorkbench(refreshed, {
      selectStage,
      expandStage,
      setActiveStepId,
      setPipelineSubTab,
    });
  };

  const saveAndContinue = async () => {
    if (!runId || guardBusy(jobRunning, actionBusy || busy, showToast)) return;
    setSaving(true);
    setCheckpointBusy(true);
    try {
      await dockRef.current?.flushPendingSaves();
      await api(`/api/runs/${runId}/transcript/reuse-edit/complete`, {
        method: "POST",
      });
      const summary = formatCorrectionSummary(correctionStats);
      showToast(
        summary ? `Reuse edit saved — ${summary}.` : "Reused transcript confirmed.",
        "success",
      );
      if (runId) markTranscriptReuseEditConsumed(runId);
      closeTranscriptReuseEdit();
      await afterCloseContinue();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Failed to save transcript", "error");
    } finally {
      setSaving(false);
      setCheckpointBusy(false);
    }
  };

  const dismissEdit = async () => {
    if (!runId || guardBusy(jobRunning, actionBusy || busy, showToast)) return;
    markTranscriptReuseEditConsumed(runId);
    setDismissing(true);
    setCheckpointBusy(true);
    try {
      await api(`/api/runs/${runId}/transcript/reuse-edit/dismiss`, {
        method: "POST",
      });
      closeTranscriptReuseEdit();
      await refreshRun();
      showToast("Using copied transcript — edit in STT review if needed.", "info");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Failed to dismiss edit", "error");
    } finally {
      setDismissing(false);
      setCheckpointBusy(false);
    }
  };

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="transcript-reuse-edit-title">
      <div className="modal-card panel modal-lg transcript-reuse-edit-modal">
        <div className="modal-head">
          <h3 id="transcript-reuse-edit-title">Review reused transcript</h3>
        </div>
        <p className="lead modal-summary">
          One-time edit after reuse. Double-click words to correct; use Fix similar words for
          repeated mishearings across the whole transcript, then save — the next reuse will pick up
          these corrections.
        </p>
        <div
          className="transcript-reuse-edit-dock"
          data-testid="transcript-reuse-edit-dock"
        >
          {dockReady ? (
            <TranscriptDockViewer
              ref={dockRef}
              fillHeight
              manageFlushPrep={false}
              onCorrectionStatsChange={setCorrectionStats}
            />
          ) : null}
        </div>
        {correctionStats.total > 0 ? (
          <p className="muted transcript-reuse-edit-stats">{formatCorrectionSummary(correctionStats)}</p>
        ) : null}
        <div className="modal-footer modal-actions">
          <button
            type="button"
            className="btn ghost"
            disabled={busy}
            onClick={() => void dismissEdit()}
            data-action-id="gui.transcript_reuse.dismiss_edit"
          >
            {dismissing ? (
              <>
                <span className="spinner-inline" aria-hidden /> Skipping…
              </>
            ) : (
              "Skip — edit later in STT review"
            )}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            onClick={() => void saveAndContinue()}
            data-testid="transcript-reuse-save-continue"
            data-action-id="gui.transcript_reuse.save_and_continue"
          >
            {saving ? (
              <>
                <span className="spinner-inline" aria-hidden /> Saving…
              </>
            ) : (
              "Save & continue"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
