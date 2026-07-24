import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatMs } from "../../utils";
import { registerStepPrimaryPrep } from "../../utils/stepPrimaryPrep";
import {
  formatCorrectionSummary,
  TranscriptDockViewer,
  type TranscriptCorrectionStats,
  type TranscriptDockHandle,
} from "../workspace/TranscriptDockViewer";
import { ArtifactAudio } from "../shared/ArtifactAudio";
import { emptyCorrectionStats } from "../../utils/transcriptCorrectionStats";
import { formatApiError } from "../../utils/safeApi";
import {
  chunkClipUrl,
  chunkFocusRange,
  chunkPlaybackRange,
} from "../../utils/transcriptReviewChunk";
import type { TranscriptWord } from "../../types";

function chunkTextFromWords(
  words: TranscriptWord[],
  startMs: number,
  endMs: number,
): string {
  return words
    .filter((w) => w.start_ms < endMs && w.end_ms > startMs)
    .map((w) => w.text)
    .join(" ");
}

export function TranscriptReviewPanel() {
  const {
    run,
    refreshRun,
    showToast,
    appendClientLog,
    loadTranscriptReview,
    transcriptReview,
  } = useApp();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [clipLoadError, setClipLoadError] = useState(false);
  const [correctionStats, setCorrectionStats] = useState<TranscriptCorrectionStats>(
    emptyCorrectionStats(),
  );
  const [draftRevision, setDraftRevision] = useState(0);
  const indexRef = useRef(0);
  const dockRef = useRef<TranscriptDockHandle>(null);
  const chunkDraftsRef = useRef<Map<string, string>>(new Map());
  const chunkDirtyRef = useRef<Set<string>>(new Set());

  const reportError = (reason: unknown, label: string) => {
    const msg = formatApiError(reason, label);
    setError(msg);
    appendClientLog(msg, "error", "transcript_review");
  };

  const chunks = transcriptReview?.chunks || [];
  const idx = Math.min(index, Math.max(0, chunks.length - 1));
  const chunk = chunks[idx];

  useEffect(() => {
    setLoading(true);
    void loadTranscriptReview()
      .then(() => setLoading(false))
      .catch((reason) => {
        reportError(reason, "Transcript review");
        setLoading(false);
      });
  }, [loadTranscriptReview]);

  useEffect(() => {
    indexRef.current = idx;
  }, [idx]);

  useEffect(() => {
    setClipLoadError(false);
  }, [chunk?.chunk_id]);

  const saveChunkToServer = async (chunkId: string, bodyText: string) => {
    if (!run) return;
    await api(`/api/runs/${run.run_id}/transcript-review/${chunkId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: bodyText, reviewed: true }),
    });
  };

  // transcript_dock_flush is registered by TranscriptDockViewer (all dock embeds).
  useEffect(() => {
    registerStepPrimaryPrep("transcript_review_flush", async () => {
      if (!run) return;
      const dirtyIds = new Set(chunkDirtyRef.current);
      try {
        for (const chunkId of dirtyIds) {
          const draft = chunkDraftsRef.current.get(chunkId);
          if (draft === undefined) continue;
          await saveChunkToServer(chunkId, draft);
        }
        chunkDraftsRef.current.clear();
        chunkDirtyRef.current.clear();
        setDraftRevision((n) => n + 1);
        await loadTranscriptReview();
        await refreshRun();
      } catch (reason) {
        reportError(reason, "Save transcript chunks");
        throw reason;
      }
    });
    return () => registerStepPrimaryPrep("transcript_review_flush", null);
  }, [run, loadTranscriptReview, refreshRun]);

  const handleLocalWordsChange = useCallback(
    (words: TranscriptWord[]) => {
      const c = chunks[indexRef.current];
      if (!c) return;
      const synced = chunkTextFromWords(words, c.start_ms, c.end_ms);
      chunkDraftsRef.current.set(c.chunk_id, synced);
      chunkDirtyRef.current.add(c.chunk_id);
      setDraftRevision((n) => n + 1);
    },
    [chunks],
  );

  const goToIndex = (next: number) => {
    indexRef.current = next;
    setIndex(next);
  };

  const clipUrl = run && chunk ? chunkClipUrl(run.run_id, chunk) : "";
  const playbackRange = chunk ? chunkPlaybackRange(chunk) : null;

  const playClipInDock = () => {
    if (!playbackRange) return;
    dockRef.current?.playClipRange(playbackRange.start_ms, playbackRange.end_ms);
  };

  const isChunkDraftDirty = (chunkId: string) => chunkDirtyRef.current.has(chunkId);
  void draftRevision;

  if (loading) {
    return (
      <div className="gate-loading-skeleton panel-inset" aria-busy>
        <p className="hint">Loading transcript review queue…</p>
      </div>
    );
  }

  if (error) return <p className="empty-state">{error}</p>;

  if (!chunks.length) {
    return <p className="empty-state">No review clips — run STT review prep first.</p>;
  }

  const confPct = Math.round((chunk.confidence ?? 0) * 100);
  const confClass =
    (chunk.confidence ?? 0) < (transcriptReview?.low_confidence_threshold || 0.85)
      ? "low"
      : "ok";
  const focusRange = chunkFocusRange(chunk, `Clip #${idx + 1}`);
  const pendingCount = transcriptReview?.pending_count ?? 0;
  const showNativeClipPlayer = Boolean(clipUrl) && !clipLoadError;
  const clipUnavailable =
    chunk.clip_ready === false || clipLoadError || (!clipUrl && chunk.clip_path);
  const hasLocalDrafts =
    chunkDirtyRef.current.size > 0 || Boolean(dockRef.current?.hasPendingSaves?.());

  return (
    <div className="tr-review-panel">
      <p className="hint sm tr-review-panel-hint">
        Edit words in the transcript below. Changes save when you finish with{" "}
        <strong>Save and complete review</strong> (banner) or{" "}
        <strong>Complete transcript review</strong> (step footer).
        {pendingCount > 0
          ? ` (${pendingCount} clip${pendingCount === 1 ? "" : "s"} not yet marked reviewed)`
          : null}
        {hasLocalDrafts ? " Unsaved local edits pending." : null}
      </p>

      <div className="tr-review-compact-bar">
        <div className="tr-review-nav">
          <button
            type="button"
            className="btn sm ghost"
            disabled={idx === 0}
            onClick={() => goToIndex(Math.max(0, idx - 1))}
          >
            Previous
          </button>
          <button
            type="button"
            className="btn sm ghost"
            disabled={idx >= chunks.length - 1}
            onClick={() => goToIndex(Math.min(chunks.length - 1, idx + 1))}
          >
            Next
          </button>
          <select
            className="select sm"
            value={idx}
            onChange={(e) => goToIndex(Number(e.target.value))}
          >
            {chunks.map((c, i) => (
              <option key={c.chunk_id} value={i}>
                #{c.rank} {c.chunk_id}
                {c.reviewed ? " ✓" : ""}
                {isChunkDraftDirty(c.chunk_id) ? " *" : ""} (
                {Math.round((c.confidence || 0) * 100)}%)
              </option>
            ))}
          </select>
        </div>
        <div className="tr-review-meta">
          <span>
            Clip <strong>{idx + 1}</strong>/<strong>{chunks.length}</strong>
          </span>
          <span className={`tr-conf ${confClass}`}>{confPct}%</span>
          <span className="muted">{transcriptReview?.pending_count ?? 0} pending</span>
          <span className="muted tr-review-time">
            {formatMs(playbackRange!.start_ms)}–{formatMs(playbackRange!.end_ms)}
          </span>
        </div>
        <div className="tr-review-playback">
          {showNativeClipPlayer ? (
            <ArtifactAudio
              key={chunk.chunk_id}
              reloadKey={chunk.chunk_id}
              className="tr-chunk-audio tr-chunk-audio--compact"
              src={clipUrl}
              onError={() => setClipLoadError(true)}
            />
          ) : clipUnavailable ? (
            <p className="hint sm tr-clip-missing">
              Pre-cut clip unavailable — use <strong>Play clip in dock</strong> or re-run{" "}
              <code>transcript_review_build</code>.
            </p>
          ) : null}
          <button
            type="button"
            className="btn sm ghost tr-play-clip-dock"
            data-testid="transcript-play-clip-dock"
            onClick={playClipInDock}
          >
            Play clip in dock
          </button>
        </div>
      </div>

      <section className="tr-review-dock-section">
        <TranscriptDockViewer
          ref={dockRef}
          focusRange={focusRange}
          seekOnFocus
          fillHeight
          onLocalWordsChange={handleLocalWordsChange}
          onCorrectionStatsChange={setCorrectionStats}
        />
      </section>

      {correctionStats.total > 0 ? (
        <p className="tr-correction-summary">{formatCorrectionSummary(correctionStats)}</p>
      ) : null}
    </div>
  );
}
