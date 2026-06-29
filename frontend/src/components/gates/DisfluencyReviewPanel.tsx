import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatMs } from "../../utils";
import { formatApiError } from "../../utils/safeApi";

interface DisfluencyEvent {
  event_id: string;
  start_ms: number;
  end_ms: number;
  speaker_id?: string;
  text?: string;
  confidence?: number;
  source?: string;
  clip_path?: string;
  review_status: string;
  include_in_restore?: boolean;
}

interface DisfluencyReviewState {
  ready?: boolean;
  status?: string;
  events?: DisfluencyEvent[];
  stats?: { total?: number; pending?: number; confirmed?: number; rejected?: number };
  pending_count?: number;
  review_complete?: boolean;
}

export function DisfluencyReviewPanel() {
  const { run, refreshRun, advanceFromCheckpoint, showToast, appendClientLog, config } = useApp();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<DisfluencyReviewState | null>(null);
  const [index, setIndex] = useState(0);

  const reportError = (reason: unknown, label: string) => {
    const msg = formatApiError(reason, label);
    setError(msg);
    showToast(msg, "error");
    appendClientLog(msg, "error", "disfluency_review");
  };

  const load = async () => {
    if (!run) return null;
    const data = await api<DisfluencyReviewState>(`/api/runs/${run.run_id}/disfluency-review`);
    setState(data);
    setError(null);
    return data;
  };

  useEffect(() => {
    setLoading(true);
    void load()
      .then(() => setLoading(false))
      .catch((reason) => {
        reportError(reason, "Disfluency review");
        setLoading(false);
      });
  }, [run?.run_id]);

  if (!config?.disfluency_extract_enabled) {
    return (
      <p className="hint">
        Disfluency extract is disabled. Enable <code>disfluency_extract.enabled</code> in{" "}
        <code>config/app.defaults.json</code> — see{" "}
        <code>docs/cross-cutting/config-keys.md</code>.
      </p>
    );
  }

  if (loading) {
    return (
      <div className="gate-loading-skeleton panel-inset" aria-busy>
        <p className="hint">Loading disfluency review…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="gate-actions">
        <p className="empty-state error-text" role="alert">
          {error}
        </p>
        <button type="button" className="btn ghost sm" onClick={() => void load()}>
          Retry
        </button>
      </div>
    );
  }

  const events = state?.events || [];
  const noAssets =
    state?.status === "no_assets" ||
    state?.status === "disabled" ||
    (state?.ready && !events.length);

  if (noAssets) {
    return (
      <div className="gate-actions">
        <p className="hint">
          {state?.status === "disabled"
            ? "Disfluency extract is disabled for this run."
            : "No filler clip assets were extracted — the pipeline will continue automatically."}
        </p>
      </div>
    );
  }

  const idx = Math.min(index, events.length - 1);
  const ev = events[idx];
  const clipUrl = ev.clip_path
    ? `/api/runs/${run!.run_id}/audio?path=${encodeURIComponent(ev.clip_path)}`
    : "";

  async function finishIfReviewComplete(reviewComplete?: boolean) {
    if (!reviewComplete) {
      await refreshRun();
      return;
    }
    showToast("Disfluency review complete");
    await refreshRun();
    await advanceFromCheckpoint();
  }

  async function saveEvent(reviewStatus: "confirmed" | "rejected") {
    if (!run) return;
    try {
      const res = await api<{ review_complete?: boolean }>(
        `/api/runs/${run.run_id}/disfluency-review/${ev.event_id}`,
        {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          review_status: reviewStatus,
          include_in_restore: reviewStatus === "confirmed",
        }),
      });
      showToast(reviewStatus === "confirmed" ? "Event confirmed" : "Event rejected");
      const data = await load();
      const pending = data?.events?.filter((e) => e.review_status === "pending") || [];
      if (pending.length && idx < events.length - 1) setIndex(idx + 1);
      await finishIfReviewComplete(res.review_complete);
    } catch (reason) {
      reportError(reason, "Save disfluency event");
    }
  }

  async function toggleIncludeInRestore(checked: boolean) {
    if (!run || ev.review_status !== "confirmed") return;
    try {
      await api(`/api/runs/${run.run_id}/disfluency-review/${ev.event_id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ review_status: "confirmed", include_in_restore: checked }),
      });
      showToast(checked ? "Included in restore" : "Excluded from restore");
      await load();
      await refreshRun();
    } catch (reason) {
      reportError(reason, "Update restore flag");
    }
  }

  async function confirmAllPending() {
    if (!run) return;
    try {
      const pending = events.filter((e) => e.review_status === "pending");
      let reviewComplete = false;
      for (const event of pending) {
        const res = await api<{ review_complete?: boolean }>(
          `/api/runs/${run.run_id}/disfluency-review/${event.event_id}`,
          {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            review_status: "confirmed",
            include_in_restore: true,
          }),
        });
        reviewComplete = Boolean(res.review_complete);
      }
      showToast(
        pending.length
          ? `Confirmed ${pending.length} filler clip${pending.length === 1 ? "" : "s"}`
          : "No pending clips",
      );
      await load();
      await finishIfReviewComplete(reviewComplete);
    } catch (reason) {
      reportError(reason, "Confirm all pending");
    }
  }

  const stats = state?.stats;

  return (
    <>
      <p className="hint">
        Listen to each filler clip. Confirm to allow restore in Flow 1 assembly, or reject false positives.
      </p>
      <div className="tr-review-header">
        <span>
          Event {idx + 1} / {events.length}
        </span>
        {stats && (
          <span className="tr-stats">
            {stats.confirmed ?? 0} confirmed · {stats.rejected ?? 0} rejected · {stats.pending ?? 0} pending
          </span>
        )}
        {(stats?.pending ?? 0) > 0 ? (
          <button
            type="button"
            className="btn ghost sm"
            data-testid="disfluency-confirm-all"
            onClick={() => void confirmAllPending()}
          >
            Confirm all pending
          </button>
        ) : null}
      </div>
      <div className="disfluency-event-card">
        <div className="disfluency-meta">
          <span>{formatMs(ev.start_ms)} – {formatMs(ev.end_ms)}</span>
          {ev.speaker_id && <span>{ev.speaker_id}</span>}
          {ev.source && <span className="badge">{ev.source}</span>}
          {ev.confidence != null && <span>{Math.round(ev.confidence * 100)}% conf</span>}
        </div>
        <p className="disfluency-text">{ev.text || "(no text)"}</p>
        {clipUrl ? (
          <audio controls src={clipUrl} className="tr-audio" />
        ) : (
          <p className="hint sm">Clip file missing — re-run disfluency extract if needed.</p>
        )}
        {ev.review_status === "confirmed" && (
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={ev.include_in_restore !== false}
              onChange={(e) => void toggleIncludeInRestore(e.target.checked)}
            />
            Include in assembly restore
          </label>
        )}
        <div className="flow-choice">
          <button type="button" className="btn ghost sm" disabled={idx <= 0} onClick={() => setIndex(idx - 1)}>
            Previous
          </button>
          <button type="button" className="btn ghost sm" onClick={() => void saveEvent("rejected")}>
            Reject
          </button>
          <button type="button" className="btn primary sm" onClick={() => void saveEvent("confirmed")}>
            Confirm
          </button>
          <button
            type="button"
            className="btn ghost sm"
            disabled={idx >= events.length - 1}
            onClick={() => setIndex(idx + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </>
  );
}
