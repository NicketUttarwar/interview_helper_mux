import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { GatePanelShell } from "../pipeline/GatePanelShell";
import {
  APPLE_PODCASTS_PASSTHROUGH_NOTICE,
  applePodcastsPassthroughUrl,
  normalizePublicFeedUrl,
} from "../../utils/applePodcastsPassthrough";
import {
  GPublishReviewSection,
  type GPublishReviewState,
  type GPublishSaveFn,
} from "./GPublishReviewSection";

const SYNC_REQUEST_TIMEOUT_MS = 25_000;

interface GPublishPayload {
  pending: boolean;
  enabled?: boolean;
  podcast_id?: string;
  show_title?: string;
  feed_url?: string | null;
  feed_base_url?: string | null;
  apple_podcasts_passthrough_url?: string | null;
  skipped?: boolean;
  cleared?: boolean;
  package_ready?: boolean;
  package_complete?: boolean;
  missing_files?: string[];
  has_master?: boolean;
  ready_package_count?: number;
  already_uploaded_count?: number;
  incomplete_count?: number;
  execution_id?: string;
  publish_result?: Record<string, unknown>;
  last_sync?: Record<string, unknown>;
  sync_job?: Record<string, unknown>;
  /** Title, cover, and master — present so the review form can paint without a second fetch. */
  review?: GPublishReviewState | null;
}

type PublishPhase =
  | "idle"
  | "saving"
  | "preparing"
  | "starting"
  | "uploading"
  | "success"
  | "error";

function isPackageReady(data: GPublishPayload | null | undefined): boolean {
  if (!data) return false;
  const missing = Array.isArray(data.missing_files) ? data.missing_files : [];
  return (
    data.package_complete === true ||
    data.package_ready === true ||
    Number(data.ready_package_count || 0) >= 1 ||
    (missing.length === 0 && Boolean(data.has_master) && Boolean(data.cleared || data.pending))
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/** Ship gate: one primary action — save edits (if any), prepare package, upload this run to S3. */
export function GPublishPanel() {
  const { runId, refreshRun, appendClientLog, showToast } = useApp();
  const [payload, setPayload] = useState<GPublishPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewDirty, setReviewDirty] = useState(false);
  const [publishPhase, setPublishPhase] = useState<PublishPhase>("idle");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const saveReviewRef = useRef<GPublishSaveFn | null>(null);
  const watchingSyncRef = useRef(false);

  const registerSave = useCallback((fn: GPublishSaveFn | null) => {
    saveReviewRef.current = fn;
  }, []);

  const gateLoadRef = useRef<Promise<GPublishPayload | null> | null>(null);
  const reload = useCallback(async (): Promise<GPublishPayload | null> => {
    if (!runId) return null;
    // Share one in-flight load. A second caller used to get null and the
    // prepare loop treated that as "package not ready" forever.
    if (gateLoadRef.current) return gateLoadRef.current;
    const task = (async (): Promise<GPublishPayload | null> => {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const data = await api<GPublishPayload>(`/api/runs/${runId}/g-publish`, {
            signal: AbortSignal.timeout(8_000),
          });
          setPayload(data);
          return data;
        } catch {
          // Keep last good snapshot — a dropped fetch must not blank the Ship UI.
          if (attempt < 2) await sleep(400 * (attempt + 1));
        }
      }
      return null;
    })();
    gateLoadRef.current = task;
    try {
      return await task;
    } finally {
      if (gateLoadRef.current === task) gateLoadRef.current = null;
    }
  }, [runId]);

  useEffect(() => {
    if (payload?.review || payload?.has_master) return;
    let cancelled = false;
    const tick = () => {
      if (!cancelled) void reload();
    };
    tick();
    const t = window.setInterval(tick, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [reload, payload?.review, payload?.has_master]);

  const applySyncTerminal = useCallback(
    (data: GPublishPayload) => {
      if (!runId) return false;
      const sj = data.sync_job || {};
      if (String(sj.execution_id || "") !== runId) return false;
      if (sj.status === "running") {
        setPublishPhase("uploading");
        setStatusMessage(String(sj.message || "Uploading this run to S3…"));
        return false;
      }
      watchingSyncRef.current = false;
      if (sj.status === "error") {
        const errs = (sj.result as { errors?: Array<{ error?: string }> } | undefined)?.errors;
        const detail =
          (Array.isArray(errs) && errs[0]?.error) ||
          sj.message ||
          sj.error ||
          "Upload failed";
        setPublishPhase("error");
        setStatusMessage(String(detail));
        setBusy(false);
        return true;
      }
      if (sj.status === "done") {
        const uploaded =
          Number(data.already_uploaded_count || 0) >= 1 ||
          Boolean((data.publish_result as { uploaded?: boolean } | undefined)?.uploaded);
        const msg = String(sj.message || "Upload finished");
        setPublishPhase("success");
        setStatusMessage(
          uploaded
            ? `Published — this run is on S3. ${msg}`
            : `Upload finished. ${msg}`,
        );
        setBusy(false);
        showToast(uploaded ? "Published — this run is on S3" : "Upload finished", "success");
        void refreshRun();
        return true;
      }
      return false;
    },
    [runId, refreshRun, showToast],
  );

  useEffect(() => {
    if (!payload || !runId) return;
    const sj = payload.sync_job || {};
    if (String(sj.execution_id || "") !== runId) return;
    if (sj.status === "running") {
      watchingSyncRef.current = true;
      setBusy(true);
    }
    if (sj.status === "running" || sj.status === "error" || sj.status === "done") {
      applySyncTerminal(payload);
    }
  }, [payload, runId, applySyncTerminal]);

  useEffect(() => {
    if (!runId) return;
    const job = payload?.sync_job || {};
    const thisRunJob =
      String(job.execution_id || "") === runId &&
      (job.status === "running" || watchingSyncRef.current);
    if (!thisRunJob && job.status !== "running") return;

    const t = window.setInterval(() => {
      void reload().then((data) => {
        if (!data) return;
        applySyncTerminal(data);
      });
    }, 1500);
    return () => window.clearInterval(t);
  }, [runId, payload?.sync_job?.status, payload?.sync_job?.execution_id, reload, applySyncTerminal]);

  if (!runId || payload?.enabled === false) return null;
  if (!payload) {
    return (
      <div data-partial-auto-checkpoint="g_publish" data-testid="g-publish-loading">
        <GatePanelShell complete={false} title="G-Publish">
          <p className="hint">Loading publish review…</p>
        </GatePanelShell>
      </div>
    );
  }
  if (!payload.pending && !payload.has_master && !payload.package_ready && !payload.cleared) {
    return null;
  }

  const feedUrl = normalizePublicFeedUrl(payload.feed_url);
  const passthroughUrl = applePodcastsPassthroughUrl(feedUrl);
  const syncJob = payload.sync_job || {};
  const syncIsThisRun = String(syncJob.execution_id || "") === runId;
  const syncRunning = syncIsThisRun && syncJob.status === "running";
  const thisRunReady = isPackageReady(payload);
  const thisRunUploaded =
    Number(payload.already_uploaded_count || 0) >= 1 ||
    Boolean((payload.publish_result as { uploaded?: boolean } | undefined)?.uploaded) ||
    (Boolean(payload.cleared && !payload.skipped) &&
      Number(payload.already_uploaded_count || 0) >= 1);
  const showReview = Boolean(payload.package_ready || payload.has_master || thisRunReady || payload.pending);

  const startS3Upload = async (): Promise<void> => {
    flushSync(() => {
      setPublishPhase("uploading");
      setStatusMessage("Contacting server to start S3 upload…");
    });

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), SYNC_REQUEST_TIMEOUT_MS);
    let started: { ok?: boolean; started?: boolean; job?: Record<string, unknown> };
    try {
      started = await api<{ ok?: boolean; started?: boolean; job?: Record<string, unknown> }>(
        `/api/runs/${runId}/g-publish/sync`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
          signal: controller.signal,
        },
      );
    } finally {
      window.clearTimeout(timeoutId);
    }
    watchingSyncRef.current = true;
    setPublishPhase("uploading");
    setStatusMessage(
      String(
        (started.job as { message?: string } | undefined)?.message ||
          "Uploading this run to S3 (additive, this execution only)…",
      ),
    );
    appendClientLog(
      "G-Publish — uploading this run's package to S3",
      "action",
      "podcast_publish",
      "gui.g_publish.sync",
    );
    showToast("Uploading this run to S3…", "info");
    const latest = await reload();
    if (latest && applySyncTerminal(latest)) {
      return;
    }
  };

  const publishToS3 = async () => {
    flushSync(() => {
      setBusy(true);
      setPublishPhase("saving");
      setStatusMessage(
        reviewDirty ? "Saving title/cover edits…" : "Checking package, then uploading…",
      );
    });
    try {
      if (reviewDirty) {
        if (!saveReviewRef.current) {
          setPublishPhase("error");
          setStatusMessage("Could not save review — reload the page and try again.");
          setBusy(false);
          return;
        }
        const ok = await saveReviewRef.current();
        if (!ok) {
          setPublishPhase("error");
          setStatusMessage("Could not save review — fix title/description, then try again.");
          setBusy(false);
          return;
        }
        setReviewDirty(false);
      }

      // One click starts upload. The server finishes a missing local package
      // in the same background job — the button does not wait on that.
      flushSync(() => {
        setPublishPhase("uploading");
        setStatusMessage("Starting S3 upload…");
      });
      await startS3Upload();
    } catch (err) {
      const msg = String(err);
      if (msg.toLowerCase().includes("already running")) {
        watchingSyncRef.current = true;
        setPublishPhase("uploading");
        setBusy(true);
        setStatusMessage("Upload already in progress for this run…");
        return;
      }
      watchingSyncRef.current = false;
      const aborted =
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError");
      const shown = aborted
        ? "Publish request timed out — the server was too busy. Hard-refresh and try again."
        : msg;
      setPublishPhase("error");
      setStatusMessage(shown);
      showToast(shown, "error");
      setBusy(false);
    }
  };

  const skip = async () => {
    setBusy(true);
    setPublishPhase("idle");
    setStatusMessage("Skipping S3 upload for this run…");
    try {
      await api<{ ok?: boolean }>(`/api/runs/${runId}/g-publish/skip`, { method: "POST" });
      appendClientLog("G-Publish skipped", "action", "podcast_publish", "gui.g_publish.skip");
      await refreshRun();
      setPayload({ ...payload, pending: false, skipped: true, cleared: false });
      setStatusMessage("Skipped — local package kept; nothing uploaded.");
      showToast("G-Publish skipped", "info");
    } catch (err) {
      setPublishPhase("error");
      setStatusMessage(String(err));
      showToast(String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const inFlight =
    busy ||
    syncRunning ||
    publishPhase === "saving" ||
    publishPhase === "preparing" ||
    publishPhase === "starting" ||
    publishPhase === "uploading";

  const bannerClass =
    publishPhase === "error"
      ? "g-publish-status error"
      : publishPhase === "success" || thisRunUploaded
        ? "g-publish-status success"
        : inFlight
          ? "g-publish-status progress"
          : "g-publish-status";

  const phaseLabel =
    publishPhase === "error"
      ? "Publish failed"
      : publishPhase === "success" || thisRunUploaded
        ? "Published"
        : publishPhase === "saving"
          ? "Saving…"
          : publishPhase === "preparing"
            ? "Preparing package…"
            : publishPhase === "uploading" || publishPhase === "starting" || syncRunning
              ? "Uploading…"
              : payload.skipped
                ? "Skipped"
                : "Ready to publish";

  const bannerText =
    statusMessage ||
    (thisRunUploaded
      ? "This run is on S3 — publish complete."
      : payload.skipped
        ? "Skipped — local package kept; nothing uploaded."
        : thisRunReady
          ? "Listen to the master, edit title/cover if needed, then publish."
          : "Listen to the master, edit title/cover if needed, then publish (prepares the package automatically).");

  const primaryLabel = thisRunUploaded
    ? "Published"
    : publishPhase === "saving"
      ? "Saving…"
      : publishPhase === "preparing"
        ? "Preparing package…"
        : publishPhase === "uploading" || publishPhase === "starting" || syncRunning
          ? "Uploading…"
          : reviewDirty
            ? "Save & publish to S3"
            : "Publish to S3";

  return (
    <div data-partial-auto-checkpoint="g_publish">
      <GatePanelShell
        complete={Boolean(thisRunUploaded || payload.skipped || payload.cleared)}
        title={`G-Publish — ${payload.show_title ?? "Zero Shot Podcast DEMO"} RSS`}
      >
        <p className="hint">
          Review title, description, and cover. One click saves any edits, finishes the local
          package if needed, and uploads this run to {payload.show_title ?? "Zero Shot Podcast DEMO"}{" "}
          (S3). Sync never deletes remote files or other executions.
        </p>

        <div
          className={bannerClass}
          role="status"
          aria-live="polite"
          data-testid="g-publish-status"
        >
          {inFlight && <span className="spinner-inline" aria-hidden />}
          <div className="g-publish-status-copy">
            <strong>{phaseLabel}</strong>
            <p>{bannerText}</p>
            {feedUrl && (publishPhase === "success" || thisRunUploaded) ? (
              <p className="hint sm">
                Feed:{" "}
                <a href={feedUrl} target="_blank" rel="noreferrer">
                  {feedUrl}
                </a>
              </p>
            ) : null}
          </div>
        </div>

        {showReview ? (
          <GPublishReviewSection
            enabled
            initialReview={payload.review}
            onDirtyChange={setReviewDirty}
            onRegisterSave={registerSave}
            onSaved={() => {
              setPublishPhase((prev) => (prev === "success" || prev === "error" ? prev : "idle"));
              void reload();
              void refreshRun();
            }}
          />
        ) : null}

        {feedUrl ? (
          <>
            <p className="hint">
              Feed URL:{" "}
              <a href={feedUrl} target="_blank" rel="noreferrer">
                {feedUrl}
              </a>
            </p>
            {passthroughUrl ? (
              <p className="hint">
                Apple Podcasts Connect pass-through:{" "}
                <a href={passthroughUrl} target="_blank" rel="noreferrer">
                  {passthroughUrl}
                </a>{" "}
                <button
                  type="button"
                  className="btn sm ghost"
                  onClick={() => {
                    void navigator.clipboard.writeText(passthroughUrl).then(
                      () => {
                        setStatusMessage("Copied Apple pass-through URL");
                        showToast("Copied Apple pass-through URL", "success");
                      },
                      () => showToast("Could not copy URL", "error"),
                    );
                  }}
                >
                  Copy
                </button>
              </p>
            ) : null}
            <p className="hint">{APPLE_PODCASTS_PASSTHROUGH_NOTICE}</p>
          </>
        ) : null}

        <div className="gate-actions-row g-publish-actions" data-testid="g-publish-actions">
          <button
            type="button"
            className="btn sm primary"
            data-testid="g-publish-upload"
            disabled={inFlight || thisRunUploaded || Boolean(payload.skipped)}
            title={
              thisRunUploaded
                ? "Already published"
                : reviewDirty
                  ? "Saves edits, prepares package if needed, then uploads"
                  : "Prepares package if needed, then uploads this run to S3"
            }
            onClick={() => void publishToS3()}
          >
            {primaryLabel}
          </button>
          {payload.pending || (payload.cleared && !thisRunUploaded && !payload.skipped) ? (
            <button
              type="button"
              className="btn sm ghost"
              data-testid="g-publish-skip"
              disabled={inFlight}
              onClick={() => void skip()}
            >
              Skip upload
            </button>
          ) : null}
        </div>
      </GatePanelShell>
    </div>
  );
}
