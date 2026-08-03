import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { GatePanelShell } from "../pipeline/GatePanelShell";

interface GPublishPayload {
  pending: boolean;
  enabled?: boolean;
  show_title?: string;
  feed_url?: string | null;
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

  const act = async (skipped: boolean) => {
    setBusy(true);
    try {
      const path = skipped ? "g-publish/skip" : "g-publish/continue";
      await api(`/api/runs/${runId}/${path}`, { method: "POST" });
      appendClientLog(
        skipped ? "G-Publish skipped" : "G-Publish cleared — ready to upload",
        "action",
        "podcast_publish",
        skipped ? "gui.g_publish.skip" : "gui.g_publish.continue",
      );
      await refreshRun();
      setPayload({ ...payload, pending: false, skipped, cleared: !skipped });
      if (!skipped) {
        showToast("Publish cleared — run podcast_publish stage to upload", "success");
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
      </p>
      {payload.feed_url ? <p className="hint">Feed base: {payload.feed_url}</p> : null}
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
