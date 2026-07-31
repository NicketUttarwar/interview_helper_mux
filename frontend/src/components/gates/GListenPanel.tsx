import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { GatePanelShell } from "../pipeline/GatePanelShell";

interface GListenPayload {
  pending: boolean;
  quality_score?: number | null;
  verdict?: string | null;
  issues?: Array<{ code?: string; message?: string; severity?: string }>;
  skipped?: boolean;
  cleared?: boolean;
}

/** Optional pre-ship listen when listen_critic score is borderline. */
export function GListenPanel() {
  const { runId, refreshRun, appendClientLog, showToast } = useApp();
  const [payload, setPayload] = useState<GListenPayload | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!runId) return;
    void api<GListenPayload>(`/api/runs/${runId}/g-listen`)
      .then(setPayload)
      .catch(() => setPayload(null));
  }, [runId]);

  if (!runId || !payload?.pending) return null;

  const continueListen = async (skipped: boolean) => {
    setBusy(true);
    try {
      const path = skipped ? "g-listen/skip" : "g-listen/continue";
      await api(`/api/runs/${runId}/${path}`, { method: "POST" });
      appendClientLog(
        skipped ? "G-Listen skipped" : "G-Listen cleared",
        "action",
        "master_finalize",
        skipped ? "gui.g_listen.skip" : "gui.g_listen.continue",
      );
      await refreshRun();
      setPayload({ ...payload, pending: false, skipped, cleared: !skipped });
    } catch (err) {
      showToast(String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <GatePanelShell title="G-Listen (optional)">
      <p className="hint">Borderline listen quality — preview assembly before shipping.</p>
      <p className="hint">
        Quality score: {payload.quality_score ?? "—"} ({payload.verdict ?? "warn"})
      </p>
      {(payload.issues?.length ?? 0) > 0 ? (
        <ul className="hint">
          {payload.issues!.slice(0, 5).map((row, i) => (
            <li key={`${row.code || "issue"}-${i}`}>{row.message || row.code}</li>
          ))}
        </ul>
      ) : null}
      <div className="gate-actions-row">
        <button
          type="button"
          className="btn sm primary"
          disabled={busy}
          onClick={() => void continueListen(false)}
        >
          Continue — sounds good
        </button>
        <button
          type="button"
          className="btn sm ghost"
          disabled={busy}
          onClick={() => void continueListen(true)}
        >
          Skip G-Listen
        </button>
      </div>
    </GatePanelShell>
  );
}
