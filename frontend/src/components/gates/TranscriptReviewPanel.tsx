import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatMs } from "../../utils";

export function TranscriptReviewPanel() {
  const { run, refreshRun, showToast, loadTranscriptReview, transcriptReview } =
    useApp();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [text, setText] = useState("");

  useEffect(() => {
    setLoading(true);
    void loadTranscriptReview()
      .then(() => setLoading(false))
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Load failed");
        setLoading(false);
      });
  }, [loadTranscriptReview]);

  const chunks = transcriptReview?.chunks || [];
  const idx = Math.min(index, Math.max(0, chunks.length - 1));
  const chunk = chunks[idx];

  useEffect(() => {
    if (chunk) setText(chunk.corrected_text || chunk.text || "");
  }, [chunk?.chunk_id]);

  const saveChunk = async (chunkId: string, reviewed: boolean, useOriginal = false) => {
    if (!run) return;
    const c = chunks.find((x) => x.chunk_id === chunkId);
    const bodyText = useOriginal ? c?.text || "" : text;
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
  };

  const complete = async (acceptUnreviewed: boolean) => {
    if (!run) return;
    try {
      await api(`/api/runs/${run.run_id}/transcript-review/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accept_unreviewed: acceptUnreviewed }),
      });
      showToast("Transcript review complete");
      await refreshRun();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Complete failed");
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

  return (
    <>
      <p className="hint">
        Clips are ranked lowest AWS confidence first. Listen, fix text, save each chunk,
        then complete review.
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
        <audio controls className="audio-player" src={clipUrl} />
        <label className="tr-label">Transcript (editable)</label>
        <textarea
          className="tr-textarea"
          rows={5}
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
      <div className="tr-review-footer">
        <button
          type="button"
          className="btn primary"
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
