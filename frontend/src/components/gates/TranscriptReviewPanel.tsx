import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatMs } from "../../utils";
import {
  formatCorrectionSummary,
  TranscriptDockViewer,
  type TranscriptCorrectionStats,
} from "../workspace/TranscriptDockViewer";
import { emptyCorrectionStats } from "../../utils/transcriptCorrectionStats";
import { formatApiError } from "../../utils/safeApi";

export function TranscriptReviewPanel() {
  const { run, refreshRun, showToast, appendClientLog, loadTranscriptReview, transcriptReview, runNextStage } =
    useApp();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [text, setText] = useState("");
  const [correctionStats, setCorrectionStats] = useState<TranscriptCorrectionStats>(
    emptyCorrectionStats(),
  );

  const reportError = (reason: unknown, label: string) => {
    const msg = formatApiError(reason, label);
    setError(msg);
    showToast(msg, "error");
    appendClientLog(msg, "error", "transcript_review");
  };

  useEffect(() => {
    setLoading(true);
    void loadTranscriptReview()
      .then(() => setLoading(false))
      .catch((reason) => {
        reportError(reason, "Transcript review");
        setLoading(false);
      });
  }, [loadTranscriptReview]);

  const chunks = transcriptReview?.chunks || [];

  if (loading) {
    return (
      <div className="gate-loading-skeleton panel-inset" aria-busy>
        <p className="hint">Loading transcript review queue…</p>
      </div>
    );
  }

  const idx = Math.min(index, Math.max(0, chunks.length - 1));
  const chunk = chunks[idx];

  useEffect(() => {
    if (chunk) setText(chunk.corrected_text || chunk.text || "");
  }, [chunk?.chunk_id, chunk?.corrected_text, chunk?.text]);

  const syncChunkTextFromDock = async () => {
    const data = await loadTranscriptReview();
    if (!data || !chunk) return;
    const updated = data.chunks.find((c) => c.chunk_id === chunk.chunk_id);
    if (updated) setText(updated.corrected_text || updated.text || "");
  };

  const saveChunk = async (chunkId: string, reviewed: boolean, useOriginal = false) => {
    if (!run) return;
    const c = chunks.find((x) => x.chunk_id === chunkId);
    const bodyText = useOriginal ? c?.text || "" : text;
    try {
      await api(`/api/runs/${run.run_id}/transcript-review/${chunkId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: bodyText, reviewed }),
      });
      showToast("Chunk saved");
      const data = await loadTranscriptReview();
      if (data) {
        const cur = data.chunks.findIndex((x) => x.chunk_id === chunkId);
        if (cur >= 0 && cur < data.chunks.length - 1) setIndex(cur + 1);
      }
      await refreshRun();
    } catch (reason) {
      reportError(reason, "Save transcript chunk");
    }
  };

  const complete = async (acceptUnreviewed: boolean) => {
    if (!run) return;
    try {
      await api(`/api/runs/${run.run_id}/transcript-review/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accept_unreviewed: acceptUnreviewed }),
      });
      const summary = formatCorrectionSummary(correctionStats);
      showToast(
        summary ? `${summary} · Transcript review complete` : "Transcript review complete",
      );
      await refreshRun();
      await runNextStage();
    } catch (reason) {
      reportError(reason, "Complete transcript review");
    }
  };

  if (loading) {
    return (
      <p className="hint">
        Clips are ranked lowest AWS confidence first. Listen, fix text, save each chunk,
        then complete review.
      </p>
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
  const clipUrl = chunk.clip_path
    ? `/api/runs/${run!.run_id}/audio?path=${encodeURIComponent(chunk.clip_path)}`
    : "";

  const focusRange = {
    start_ms: chunk.start_ms,
    end_ms: chunk.end_ms,
    label: `Clip #${idx + 1}`,
  };

  return (
    <>
      <p className="gate-progress-subheader hint sm">
        {(transcriptReview?.pending_count ?? chunks.length) > 0
          ? `${transcriptReview?.pending_count ?? chunks.length} clip(s) remaining — lowest confidence first.`
          : "Review clips below, then complete transcript review."}
      </p>
      <p className="hint">
        Use the synced transcript dock below to edit word-by-word as audio plays. Low-confidence
        clips are listed first — jump between clips or edit inline at any time.
      </p>
      <div className="tr-review-header">
        <span>
          Clip <strong>{idx + 1}</strong> of <strong>{chunks.length}</strong>
        </span>
        <span className={`tr-conf ${confClass}`}>Confidence {confPct}%</span>
        <span className="muted">
          {chunk.chunk_id} · {formatMs(chunk.start_ms)}–{formatMs(chunk.end_ms)} ·{" "}
          {chunk.speaker_id || "—"}
        </span>
        <span className="muted">{transcriptReview?.pending_count ?? 0} pending</span>
      </div>
      <div className="tr-review-nav">
        <button
          type="button"
          className="btn sm ghost"
          disabled={idx === 0}
          onClick={() => setIndex(Math.max(0, idx - 1))}
        >
          Previous
        </button>
        <button
          type="button"
          className="btn sm ghost"
          disabled={idx >= chunks.length - 1}
          onClick={() => setIndex(Math.min(chunks.length - 1, idx + 1))}
        >
          Next
        </button>
        <select
          className="select sm"
          value={idx}
          onChange={(e) => setIndex(Number(e.target.value))}
        >
          {chunks.map((c, i) => (
            <option key={c.chunk_id} value={i}>
              #{c.rank} {c.chunk_id}
              {c.reviewed ? " ✓" : ""} ({Math.round((c.confidence || 0) * 100)}%)
            </option>
          ))}
        </select>
      </div>
      <div className="tr-review-body">
        <audio controls className="audio-player tr-chunk-audio" src={clipUrl} />
        <label className="tr-label">Chunk text (bulk edit)</label>
        <textarea
          className="tr-textarea"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="tr-review-actions">
          <button
            type="button"
            className="btn primary sm"
            onClick={() => void saveChunk(chunk.chunk_id, true)}
          >
            Save chunk
          </button>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => void saveChunk(chunk.chunk_id, true, true)}
          >
            Mark reviewed (no change)
          </button>
        </div>
      </div>

      <section className="tr-review-dock-section">
        <h4>Synced transcript editor</h4>
        <TranscriptDockViewer
          focusRange={focusRange}
          seekOnFocus
          onWordsSaved={() => void syncChunkTextFromDock()}
          onCorrectionStatsChange={setCorrectionStats}
        />
      </section>

      <div className="tr-review-footer">
        {correctionStats.total > 0 ? (
          <p className="tr-correction-summary">{formatCorrectionSummary(correctionStats)}</p>
        ) : null}
        <button
          type="button"
          className="btn primary"
          data-testid="complete-transcript-review"
          onClick={() => void complete(false)}
        >
          Complete transcript review
        </button>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => void complete(true)}
        >
          Accept remaining &amp; complete
        </button>
      </div>
    </>
  );
}
