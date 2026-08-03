import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { GatePanelShell } from "../pipeline/GatePanelShell";

interface GPublishPayload {
  pending: boolean;
  enabled?: boolean;
  show_title?: string;
  feed_url?: string | null;
  feed_base_url?: string | null;
  skipped?: boolean;
  cleared?: boolean;
  package_ready?: boolean;
  has_master?: boolean;
  ready_package_count?: number;
  already_uploaded_count?: number;
  incomplete_count?: number;
  publish_result?: Record<string, unknown>;
  last_sync?: Record<string, unknown>;
  sync_job?: Record<string, unknown>;
}

/** Ship gate: prepare local package + sync ready ASSETS packages to The War Room RSS. */
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

  const feedUrl = payload.feed_url || null;
  const result = payload.publish_result || {};
  const syncJob = payload.sync_job || {};
  const syncRunning = syncJob.status === "running";
  const readyCount = Number(payload.ready_package_count || 0);
  const uploadedCount = Number(payload.already_uploaded_count || 0);

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

  const syncAll = async () => {
    setBusy(true);
    try {
      await api<{ ok?: boolean; started?: boolean }>(`/api/runs/${runId}/g-publish/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      appendClientLog(
        "G-Publish — syncing all ready ASSETS packages to S3",
        "action",
        "podcast_publish",
        "gui.g_publish.sync",
      );
      reload();
      showToast("Uploading ready packages to S3 (additive, no deletes)", "success");
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
        Mastering is separate from RSS. Prepare a local package for this run, then upload all ready
        packages under ASSETS to {payload.show_title ?? "The War Room"} (S3 + CloudFront). Sync never
        deletes remote files and skips executions already on S3.
      </p>
      <p className="hint">
        Ready to upload: {readyCount} · Already on S3: {uploadedCount}
        {typeof payload.incomplete_count === "number" && payload.incomplete_count > 0
          ? ` · Incomplete (master only): ${payload.incomplete_count}`
          : null}
      </p>
      {feedUrl ? (
        <p className="hint">
          Feed URL:{" "}
          <a href={feedUrl} target="_blank" rel="noreferrer">
            {feedUrl}
          </a>
        </p>
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
          disabled={busy || syncRunning || readyCount < 1}
          onClick={() => void syncAll()}
        >
          {syncRunning ? "Uploading…" : "Upload all ready packages to S3"}
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
