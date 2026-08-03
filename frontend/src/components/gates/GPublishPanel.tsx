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
  publish_result?: Record<string, unknown>;
}

/** Ship gate: publish episode package to The War Room RSS (S3 + CloudFront). */
export function GPublishPanel() {
  const { runId, refreshRun, appendClientLog, showToast } = useApp();
  const [payload, setPayload] = useState<GPublishPayload | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!runId) return;
    void api<GPublishPayload>(`/api/runs/${runId}/g-publish`)
      .then(setPayload)
      .catch(() => setPayload(null));
  }, [runId]);

  if (!runId || !payload?.pending || payload.enabled === false) return null;

  const feedUrl = payload.feed_url || null;
  const result = payload.publish_result || {};

  const act = async (skipped: boolean) => {
    setBusy(true);
    try {
      const path = skipped ? "g-publish/skip" : "g-publish/continue";
      const res = await api<{ ok?: boolean; started?: boolean }>(`/api/runs/${runId}/${path}`, {
        method: "POST",
      });
      appendClientLog(
        skipped ? "G-Publish skipped" : "G-Publish cleared — publishing episode package",
        "action",
        "podcast_publish",
        skipped ? "gui.g_publish.skip" : "gui.g_publish.continue",
      );
      await refreshRun();
      setPayload({ ...payload, pending: false, skipped, cleared: !skipped });
      if (!skipped) {
        showToast(
          res?.started
            ? "Publishing to RSS — episode package running"
            : "Publish cleared — episode package starting",
          "success",
        );
      }
    } catch (err) {
      showToast(String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <GatePanelShell title="G-Publish — The War Room RSS">
      <p className="hint">
        Upload the mastered episode to {payload.show_title ?? "The War Room"} (S3 + CloudFront feed).
        Continue clears the gate and runs the publish stages through upload.
      </p>
      {feedUrl ? (
        <p className="hint">
          Feed URL:{" "}
          <a href={feedUrl} target="_blank" rel="noreferrer">
            {feedUrl}
          </a>
        </p>
      ) : null}
      {typeof result.enclosure_url === "string" ? (
        <p className="hint">Last enclosure: {String(result.enclosure_url)}</p>
      ) : null}
      {typeof result.invalidation_id === "string" && result.invalidation_id ? (
        <p className="hint">Last invalidation: {String(result.invalidation_id)}</p>
      ) : null}
      {typeof result.episode_number === "number" ? (
        <p className="hint">Last episode #: {String(result.episode_number)}</p>
      ) : null}
      <div className="gate-actions-row">
        <button
          type="button"
          className="btn sm primary"
          disabled={busy}
          onClick={() => void act(false)}
        >
          Publish to RSS
        </button>
        <button type="button" className="btn sm ghost" disabled={busy} onClick={() => void act(true)}>
          Skip publish
        </button>
      </div>
    </GatePanelShell>
  );
}
