import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { GatePanelShell } from "../pipeline/GatePanelShell";
import {
  APPLE_PODCASTS_PASSTHROUGH_NOTICE,
  applePodcastsPassthroughUrl,
  normalizePublicFeedUrl,
} from "../../utils/applePodcastsPassthrough";
import { GPublishReviewSection } from "./GPublishReviewSection";

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

/** Ship gate: review package metadata + upload this run only to the selected catalog podcast. */
export function GPublishPanel() {
  const { runId, refreshRun, appendClientLog, showToast } = useApp();
  const [payload, setPayload] = useState<GPublishPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewDirty, setReviewDirty] = useState(false);

  const reload = () => {
    if (!runId) return;
    void api<GPublishPayload>(`/api/runs/${runId}/g-publish`)
      .then(setPayload)
      .catch(() => setPayload(null));
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when run changes
  }, [runId]);

  useEffect(() => {
    if (!runId || payload?.sync_job?.status !== "running") return;
    const t = window.setInterval(() => reload(), 2500);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, payload?.sync_job?.status]);

  if (!runId || !payload || payload.enabled === false) return null;
  if (!payload.pending && !payload.has_master && !payload.package_ready && !payload.cleared) {
    return null;
  }

  const feedUrl = normalizePublicFeedUrl(payload.feed_url);
  const passthroughUrl = applePodcastsPassthroughUrl(feedUrl);
  const syncJob = payload.sync_job || {};
  const syncRunning = syncJob.status === "running";
  const readyCount = Number(payload.ready_package_count || 0);
  const uploadedCount = Number(payload.already_uploaded_count || 0);
  const thisRunReady = readyCount >= 1;
  const thisRunUploaded = uploadedCount >= 1;
  const showReview = Boolean(payload.package_ready || payload.has_master);

  const prepare = async () => {
    setBusy(true);
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
      reload();
      showToast(
        res?.started
          ? "Preparing local episode package"
          : "Prepare cleared — package stages starting",
        "success",
      );
    } catch (err) {
      showToast(String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const syncThisRun = async () => {
    if (reviewDirty) {
      showToast("Save your review changes before uploading to S3.", "warning");
      return;
    }
    setBusy(true);
    try {
      await api<{ ok?: boolean; started?: boolean }>(`/api/runs/${runId}/g-publish/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      appendClientLog(
        "G-Publish — uploading this run's package to S3",
        "action",
        "podcast_publish",
        "gui.g_publish.sync",
      );
      reload();
      showToast("Uploading this run to S3 (additive, no deletes, this execution only)", "success");
    } catch (err) {
      showToast(String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const skip = async () => {
    setBusy(true);
    try {
      await api<{ ok?: boolean }>(`/api/runs/${runId}/g-publish/skip`, { method: "POST" });
      appendClientLog("G-Publish skipped", "action", "podcast_publish", "gui.g_publish.skip");
      await refreshRun();
      setPayload({ ...payload, pending: false, skipped: true, cleared: false });
    } catch (err) {
      showToast(String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-partial-auto-checkpoint="g_publish">
      <GatePanelShell title={`G-Publish — ${payload.show_title ?? "Zero Shot Podcast DEMO"} RSS`}>
        <p className="hint">
          Review title, description, and cover below. Listen to the final master, save your edits,
          then upload this run&apos;s package to {payload.show_title ?? "Zero Shot Podcast DEMO"}{" "}
          (S3 + CloudFront invalidation). Sync never deletes remote files or other executions.
        </p>
        <p className="hint">
          This run:{" "}
          {thisRunUploaded
            ? "already on S3"
            : thisRunReady
              ? "ready to upload"
              : payload.incomplete_count
                ? "package incomplete"
                : "not ready"}
        </p>

        {showReview ? (
          <GPublishReviewSection
            enabled
            onDirtyChange={setReviewDirty}
            onSaved={() => {
              reload();
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
                      () => showToast("Copied Apple pass-through URL", "success"),
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

        {typeof syncJob.message === "string" && syncJob.message ? (
          <p className="hint">
            Sync: {String(syncJob.status || "")} — {String(syncJob.message)}
          </p>
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
            disabled={busy || syncRunning || !thisRunReady || reviewDirty}
            title={reviewDirty ? "Save review changes first" : undefined}
            onClick={() => void syncThisRun()}
          >
            {syncRunning ? "Uploading…" : "Upload this run to S3"}
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
