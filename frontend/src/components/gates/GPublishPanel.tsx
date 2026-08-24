import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { GatePanelShell } from "../pipeline/GatePanelShell";
import {
  APPLE_PODCASTS_PASSTHROUGH_NOTICE,
  applePodcastsPassthroughUrl,
  normalizePublicFeedUrl,
} from "../../utils/applePodcastsPassthrough";

interface GPublishPayload {
  pending: boolean;
  enabled?: boolean;
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

/** Ship gate: prepare local package + upload this run only to The War Room RSS. */
export function GPublishPanel() {
  const { runId, refreshRun, appendClientLog, showToast } = useApp();
  const [payload, setPayload] = useState<GPublishPayload | null>(null);
  const [busy, setBusy] = useState(false);

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
  // Build the href locally so a stale/unexpected API string cannot become a link.
  const passthroughUrl = applePodcastsPassthroughUrl(feedUrl);
  const result = payload.publish_result || {};
  const syncJob = payload.sync_job || {};
  const syncRunning = syncJob.status === "running";
  const readyCount = Number(payload.ready_package_count || 0);
  const uploadedCount = Number(payload.already_uploaded_count || 0);
  const thisRunReady = readyCount >= 1;
  const thisRunUploaded = uploadedCount >= 1;

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
    <GatePanelShell title="G-Publish — The War Room RSS">
      <p className="hint">
        Mastering is separate from RSS. Prepare a local package for this run, then upload only this
        run&apos;s complete package to {payload.show_title ?? "The War Room"} (S3 + CloudFront). Sync
        never deletes remote files, never uploads other executions, and skips if this run is already
        on S3.
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
              Apple Podcasts Connect pass-through (copy this; pre-fills the RSS field):{" "}
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
      {payload.package_ready ? (
        <p className="hint">This run has a local package ready.</p>
      ) : null}
      {typeof result.title === "string" ? (
        <p className="hint">Package title: {String(result.title)}</p>
      ) : null}
      {typeof syncJob.message === "string" && syncJob.message ? (
        <p className="hint">
          Sync: {String(syncJob.status || "")} — {String(syncJob.message)}
        </p>
      ) : null}
      {typeof result.enclosure_url === "string" ? (
        <p className="hint">Last enclosure: {String(result.enclosure_url)}</p>
      ) : null}
      <div className="gate-actions-row">
        {payload.pending ? (
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
          disabled={busy || syncRunning || !thisRunReady}
          onClick={() => void syncThisRun()}
        >
          {syncRunning ? "Uploading…" : "Upload this run to S3"}
        </button>
        {payload.pending ? (
          <button type="button" className="btn sm ghost" disabled={busy || syncRunning} onClick={() => void skip()}>
            Skip
          </button>
        ) : null}
      </div>
    </GatePanelShell>
  );
}
