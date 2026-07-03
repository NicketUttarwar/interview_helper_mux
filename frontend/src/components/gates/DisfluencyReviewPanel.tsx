import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatMs } from "../../utils";
import { formatApiError } from "../../utils/safeApi";
import {
  disfluencyClipUrl,
  firstPendingEventIndex,
  resolveDisfluencyClipPath,
} from "../../utils/disfluencyReviewEvent";
import { guardBusy } from "../../utils/guardBusy";

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

function reviewStatusLabel(status: string): string {
  if (status === "confirmed") return "Confirmed";
  if (status === "rejected") return "Rejected";
  return "Pending";
}

export function DisfluencyReviewPanel() {
  const {
    run,
    refreshRun,
    advanceFromCheckpoint,
    completeDisfluencyReview,
    showToast,
    appendClientLog,
    config,
    actionBusy,
    jobRunning,
  } = useApp();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<DisfluencyReviewState | null>(null);
  const [index, setIndex] = useState(0);
  const [clipLoadError, setClipLoadError] = useState(false);
  const [finishing, setFinishing] = useState(false);

  useEffect(() => {
    setClipLoadError(false);
  }, [run?.run_id, index]);

  const reportError = (reason: unknown, label: string, opts?: { toast?: boolean }) => {
    const msg = formatApiError(reason, label);
    setError(msg);
    if (opts?.toast !== false) {
      showToast(msg, "error");
      appendClientLog(msg, "error", "disfluency_review");
    }
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
      .then((data) => {
        if (data?.events?.length) {
          setIndex(firstPendingEventIndex(data.events));
        }
      })
      .finally(() => setLoading(false))
      .catch((reason) => {
        reportError(reason, "Disfluency review", { toast: false });
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
  const clipUrl = run ? disfluencyClipUrl(run.run_id, ev) : "";
  const clipRel = resolveDisfluencyClipPath(ev);
  const pendingCount = state?.pending_count ?? statsPending(state);
  const stats = state?.stats;
  const busy = finishing || actionBusy || jobRunning;
  const allReviewed = pendingCount === 0;
  const showNativeClipPlayer = Boolean(clipUrl) && !clipLoadError;

  async function finishReviewWhenClear(reviewComplete?: boolean) {
    if (!run) return;
    const data = await load();
    const pending = data?.pending_count ?? 0;
    if (pending > 0) {
      await refreshRun();
      return;
    }
    setFinishing(true);
    try {
      if (!reviewComplete && !data?.review_complete) {
        await completeDisfluencyReview(false);
      } else {
        showToast("Disfluency review complete");
        await refreshRun();
        await advanceFromCheckpoint();
      }
    } catch (reason) {
      reportError(reason, "Complete disfluency review");
    } finally {
      setFinishing(false);
    }
  }

  async function saveEvent(reviewStatus: "confirmed" | "rejected") {
    if (!run || busy) return;
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
        },
      );
      showToast(reviewStatus === "confirmed" ? "Event confirmed" : "Event rejected");
      const data = await load();
      const nextEvents = data?.events ?? [];
      const nextPending = nextEvents.filter((e) => e.review_status === "pending");
      if (nextPending.length) {
        setIndex(firstPendingEventIndex(nextEvents));
      }
      await finishReviewWhenClear(res.review_complete);
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

  async function confirmAllAndContinue() {
    if (!run || guardBusy(jobRunning, actionBusy || finishing, showToast)) return;
    setFinishing(true);
    try {
      await completeDisfluencyReview(true);
    } catch (reason) {
      reportError(reason, "Confirm all pending");
    } finally {
      setFinishing(false);
    }
  }

  async function continuePipeline() {
    if (!run || guardBusy(jobRunning, actionBusy || finishing, showToast)) return;
    setFinishing(true);
    try {
      await completeDisfluencyReview(false);
    } catch (reason) {
      reportError(reason, "Continue pipeline");
    } finally {
      setFinishing(false);
    }
  }

  return (
    <div className="disfluency-review-panel">
      <p className="hint sm">
        Listen to each filler clip. Confirm to allow restore in Flow 1 assembly, or reject false
        positives. Use <strong>Confirm all &amp; continue</strong> below to accept every pending
        clip at once.
      </p>

      <div className="tr-review-header">
        <span>
          Clip <strong>{idx + 1}</strong> / <strong>{events.length}</strong>
        </span>
        {stats ? (
          <span className="tr-stats">
            {stats.confirmed ?? 0} confirmed · {stats.rejected ?? 0} rejected ·{" "}
            {stats.pending ?? 0} pending
          </span>
        ) : null}
        <span className={`badge status-${ev.review_status === "pending" ? "todo" : "done"}`}>
          {reviewStatusLabel(ev.review_status)}
        </span>
      </div>

      <div className="disfluency-event-card">
        <div className="disfluency-meta">
          <span>
            {formatMs(ev.start_ms)} – {formatMs(ev.end_ms)}
          </span>
          {ev.speaker_id ? <span>{ev.speaker_id}</span> : null}
          {ev.source ? <span className="badge">{ev.source}</span> : null}
          {ev.confidence != null ? <span>{Math.round(ev.confidence * 100)}% conf</span> : null}
        </div>
        <p className="disfluency-text">{ev.text || "(no text)"}</p>
        {showNativeClipPlayer ? (
          <audio
            key={ev.event_id}
            controls
            src={clipUrl}
            className="tr-audio"
            preload="metadata"
            onError={() => setClipLoadError(true)}
          />
        ) : clipRel ? (
          <p className="hint sm tr-clip-missing" role="alert">
            Clip could not be loaded
            {clipLoadError ? " (file missing or blocked)" : ""} — re-run{" "}
            <code>disfluency_extract</code> if needed.
          </p>
        ) : (
          <p className="hint sm">Clip file missing — re-run disfluency extract if needed.</p>
        )}
        {ev.review_status === "confirmed" ? (
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={ev.include_in_restore !== false}
              onChange={(e) => void toggleIncludeInRestore(e.target.checked)}
            />
            Include in assembly restore
          </label>
        ) : null}
        <div className="flow-choice">
          <button
            type="button"
            className="btn ghost sm"
            disabled={idx <= 0 || busy}
            onClick={() => setIndex(idx - 1)}
          >
            Previous
          </button>
          <button
            type="button"
            className="btn ghost sm"
            disabled={busy || ev.review_status !== "pending"}
            onClick={() => void saveEvent("rejected")}
          >
            Reject
          </button>
          <button
            type="button"
            className="btn primary sm"
            disabled={busy || ev.review_status !== "pending"}
            onClick={() => void saveEvent("confirmed")}
          >
            Confirm
          </button>
          <button
            type="button"
            className="btn ghost sm"
            disabled={idx >= events.length - 1 || busy}
            onClick={() => setIndex(idx + 1)}
          >
            Next
          </button>
        </div>
      </div>

      <div className="disfluency-review-actions panel-inset">
        {allReviewed ? (
          <p className="hint sm">
            All clips reviewed — continue to unlock the next pipeline stage.
          </p>
        ) : (
          <p className="hint sm">
            {pendingCount} clip{pendingCount === 1 ? "" : "s"} still pending — confirm each above
            or accept all at once.
          </p>
        )}
        <div className="flow-choice">
          {!allReviewed ? (
            <button
              type="button"
              className="btn primary"
              data-testid="disfluency-confirm-all"
              data-action-id="gui.disfluency_review.complete"
              disabled={busy}
              aria-busy={finishing || undefined}
              onClick={() => void confirmAllAndContinue()}
            >
              {finishing ? (
                <>
                  <span className="spinner-inline" aria-hidden />
                  Working…
                </>
              ) : (
                "Confirm all & continue"
              )}
            </button>
          ) : (
            <button
              type="button"
              className="btn primary"
              data-testid="complete-disfluency-review"
              data-action-id="gui.disfluency_review.complete"
              disabled={busy}
              aria-busy={finishing || undefined}
              onClick={() => void continuePipeline()}
            >
              {finishing ? (
                <>
                  <span className="spinner-inline" aria-hidden />
                  Continuing…
                </>
              ) : (
                "Continue pipeline"
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function statsPending(state: DisfluencyReviewState | null): number {
  return state?.stats?.pending ?? 0;
}
