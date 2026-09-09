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
import { GPublishReviewSection, type GPublishSaveFn } from "./GPublishReviewSection";

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
  has_master?: boolean;
  ready_package_count?: number;
  already_uploaded_count?: number;
  incomplete_count?: number;
  execution_id?: string;
  publish_result?: Record<string, unknown>;
  last_sync?: Record<string, unknown>;
  sync_job?: Record<string, unknown>;
}

type UploadPhase = "idle" | "starting" | "uploading" | "success" | "error";

/** Ship gate: review package metadata + upload this run only to the selected catalog podcast. */
export function GPublishPanel() {
  const { runId, refreshRun, appendClientLog, showToast } = useApp();
  const [payload, setPayload] = useState<GPublishPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewDirty, setReviewDirty] = useState(false);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>("idle");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const saveReviewRef = useRef<GPublishSaveFn | null>(null);
  const watchingSyncRef = useRef(false);

  const registerSave = useCallback((fn: GPublishSaveFn | null) => {
    saveReviewRef.current = fn;
  }, []);

  const reload = useCallback(async (): Promise<GPublishPayload | null> => {
    if (!runId) return null;
    try {
      const data = await api<GPublishPayload>(`/api/runs/${runId}/g-publish`);
      setPayload(data);
      return data;
    } catch {
      setPayload(null);
      return null;
    }
  }, [runId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const applySyncTerminal = useCallback(
    (data: GPublishPayload) => {
      if (!runId) return false;
      const sj = data.sync_job || {};
      if (String(sj.execution_id || "") !== runId) return false;
      if (sj.status === "running") {
        setUploadPhase("uploading");
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
        setUploadPhase("error");
        setStatusMessage(String(detail));
        setBusy(false);
        return true;
      }
      if (sj.status === "done") {
        const uploaded =
          Number(data.already_uploaded_count || 0) >= 1 ||
          Boolean((data.publish_result as { uploaded?: boolean } | undefined)?.uploaded);
        const msg = String(sj.message || "Upload finished");
        setUploadPhase(uploaded ? "success" : "success");
        setStatusMessage(uploaded ? `Uploaded to S3. ${msg}` : msg);
        setBusy(false);
        if (uploaded) void refreshRun();
        return true;
      }
      return false;
    },
    [runId, refreshRun],
  );

  // Surface an existing sync error/success for this run on load (no silent grey button).
  useEffect(() => {
    if (!payload || !runId) return;
    const sj = payload.sync_job || {};
    if (String(sj.execution_id || "") !== runId) return;
    if (sj.status === "error" || sj.status === "done") {
      applySyncTerminal(payload);
    }
  }, [payload, runId, applySyncTerminal]);

  // Poll while this run's sync job is in flight (ignore stale jobs for other executions).
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

  if (!runId || !payload || payload.enabled === false) return null;
  if (!payload.pending && !payload.has_master && !payload.package_ready && !payload.cleared) {
    return null;
  }

  const feedUrl = normalizePublicFeedUrl(payload.feed_url);
  const passthroughUrl = applePodcastsPassthroughUrl(feedUrl);
  const syncJob = payload.sync_job || {};
  const syncIsThisRun = String(syncJob.execution_id || "") === runId;
  const syncRunning = syncIsThisRun && syncJob.status === "running";
  const readyCount = Number(payload.ready_package_count || 0);
  const uploadedCount = Number(payload.already_uploaded_count || 0);
  const thisRunReady = readyCount >= 1;
  const thisRunUploaded =
    uploadedCount >= 1 ||
    Boolean((payload.publish_result as { uploaded?: boolean } | undefined)?.uploaded) ||
    (Boolean(payload.cleared && !payload.skipped) && uploadedCount >= 1);
  const showReview = Boolean(payload.package_ready || payload.has_master);

  const prepare = async () => {
    setBusy(true);
    setUploadPhase("idle");
    setStatusMessage("Preparing local episode package…");
    try {
      const res = await api<{ ok?: boolean; started?: boolean }>(
        `/api/runs/${runId}/g-publish/continue`,
        { method: "POST" },
      );
      appendClientLog(
        "G-Publish — preparing local episode package (no S3)",
        "action",
        "podcast_publish",
        "gui.g_publish.prepare",
      );
      await refreshRun();
      await reload();
      setStatusMessage(
        res?.started
          ? "Preparing local episode package — watch Activity for progress."
          : "Prepare cleared — package stages starting.",
      );
      showToast("Preparing local episode package", "success");
    } catch (err) {
      setUploadPhase("error");
      setStatusMessage(String(err));
      showToast(String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const syncThisRun = async () => {
    // Paint status before any network await — otherwise a hung serve leaves a
    // grey button with no visible feedback (React won't flush until first await).
    flushSync(() => {
      setBusy(true);
      setUploadPhase("starting");
      setStatusMessage("Starting S3 upload for this run…");
    });
    try {
      if (reviewDirty && saveReviewRef.current) {
        flushSync(() => {
          setStatusMessage("Saving review edits, then uploading…");
        });
        const ok = await saveReviewRef.current();
        if (!ok) {
          setUploadPhase("error");
          setStatusMessage("Could not save review — fix title/description, then try Upload again.");
          setBusy(false);
          return;
        }
        setReviewDirty(false);
      } else if (reviewDirty) {
        setUploadPhase("error");
        setStatusMessage("Save your review changes, then try Upload again.");
        setBusy(false);
        return;
      }

      flushSync(() => {
        setUploadPhase("uploading");
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
      setUploadPhase("uploading");
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
      // Keep busy until poll sees done/error for this run.
    } catch (err) {
      watchingSyncRef.current = false;
      const aborted =
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError");
      const msg = aborted
        ? "Upload request timed out — the server was too busy to start sync. Hard-refresh and try again."
        : String(err);
      setUploadPhase("error");
      setStatusMessage(msg);
      showToast(msg, "error");
      setBusy(false);
    }
  };

  const skip = async () => {
    setBusy(true);
    setUploadPhase("idle");
    setStatusMessage("Skipping S3 upload for this run…");
    try {
      await api<{ ok?: boolean }>(`/api/runs/${runId}/g-publish/skip`, { method: "POST" });
      appendClientLog("G-Publish skipped", "action", "podcast_publish", "gui.g_publish.skip");
      await refreshRun();
      setPayload({ ...payload, pending: false, skipped: true, cleared: false });
      setStatusMessage("G-Publish skipped — local package kept; nothing uploaded.");
      showToast("G-Publish skipped", "info");
    } catch (err) {
      setUploadPhase("error");
      setStatusMessage(String(err));
      showToast(String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const bannerClass =
    uploadPhase === "error"
      ? "g-publish-status error"
      : uploadPhase === "success" || thisRunUploaded
        ? "g-publish-status success"
        : uploadPhase === "uploading" || uploadPhase === "starting" || syncRunning
          ? "g-publish-status progress"
          : "g-publish-status";

  const bannerText =
    statusMessage ||
    (thisRunUploaded
      ? "This run is on S3."
      : thisRunReady
        ? "Local package ready — upload to S3 or skip."
        : payload.incomplete_count
          ? "Package incomplete — prepare first."
          : "Waiting for local package…");

  return (
    <div data-partial-auto-checkpoint="g_publish">
      <GatePanelShell
        complete={Boolean(thisRunUploaded || payload.skipped || payload.cleared)}
        title={`G-Publish — ${payload.show_title ?? "Zero Shot Podcast DEMO"} RSS`}
      >
        <p className="hint">
          Review title, description, and cover below. Listen to the final master, save your edits,
          then upload this run&apos;s package to {payload.show_title ?? "Zero Shot Podcast DEMO"}{" "}
          (S3 + CloudFront invalidation). Sync never deletes remote files or other executions.
        </p>

        <div
          className={bannerClass}
          role="status"
          aria-live="polite"
          data-testid="g-publish-status"
        >
          {(uploadPhase === "uploading" || uploadPhase === "starting" || syncRunning) && (
            <span className="spinner-inline" aria-hidden />
          )}
          <div className="g-publish-status-copy">
            <strong>
              {uploadPhase === "error"
                ? "Upload failed"
                : uploadPhase === "success" || thisRunUploaded
                  ? "Upload complete"
                  : uploadPhase === "uploading" || syncRunning
                    ? "Uploading…"
                    : uploadPhase === "starting"
                      ? "Starting upload…"
                      : "Publish status"}
            </strong>
            <p>{bannerText}</p>
            {feedUrl && (uploadPhase === "success" || thisRunUploaded) ? (
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
            onDirtyChange={setReviewDirty}
            onRegisterSave={registerSave}
            onSaved={() => {
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

        <div className="gate-actions-row">
          {payload.pending && !payload.package_ready ? (
            <button
              type="button"
              className="btn sm primary"
              disabled={busy || syncRunning}
              onClick={() => void prepare()}
            >
              Prepare package for this run
            </button>
          ) : null}
          <button
            type="button"
            className="btn sm primary"
            data-testid="g-publish-upload"
            disabled={busy || syncRunning || !thisRunReady || thisRunUploaded}
            title={
              thisRunUploaded
                ? "Already uploaded"
                : reviewDirty
                  ? "Will save review edits, then upload"
                  : !thisRunReady
                    ? "Local package not ready"
                    : undefined
            }
            onClick={() => void syncThisRun()}
          >
            {syncRunning || uploadPhase === "uploading"
              ? "Uploading…"
              : thisRunUploaded
                ? "Uploaded"
                : reviewDirty
                  ? "Save & upload this run to S3"
                  : "Upload this run to S3"}
          </button>
          {payload.pending ? (
            <button
              type="button"
              className="btn sm ghost"
              disabled={busy || syncRunning}
              onClick={() => void skip()}
            >
              Skip
            </button>
          ) : null}
        </div>
      </GatePanelShell>
    </div>
  );
}
