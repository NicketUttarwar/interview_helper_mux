import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";

interface Props {
  stageId: string;
}

export function DisfluencyRestorePanel({ stageId }: Props) {
  const { run, refreshRun, showToast, config } = useApp();
  const [enabled, setEnabled] = useState(true);
  const [confirmedCount, setConfirmedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!run) return;
    setEnabled(run.meta?.disfluency_restore?.enabled ?? config?.disfluency_restore_enabled ?? true);
    void api<{ stats?: { confirmed?: number } }>(`/api/runs/${run.run_id}/disfluency-review`)
      .then((data) => setConfirmedCount(data.stats?.confirmed ?? 0))
      .finally(() => setLoading(false));
  }, [run?.run_id, config?.disfluency_restore_enabled, run?.meta?.disfluency_restore?.enabled]);

  if (!config?.disfluency_restore_enabled || loading) {
    return loading ? (
      <div className="disfluency-restore-panel gate-loading-skeleton panel-inset" aria-busy>
        <span className="spinner-inline" aria-hidden /> Loading filler restore options…
      </div>
    ) : null;
  }
  if (stageId !== "edl" && stageId !== "assembly_preview") return null;

  const toggle = async () => {
    if (!run || saving) return;
    const next = !enabled;
    setSaving(true);
    showToast(next ? "Enabling filler restore…" : "Disabling filler restore…");
    try {
      await api(`/api/runs/${run.run_id}/disfluency-restore`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
      setEnabled(next);
      showToast(next ? "Filler restore enabled — re-run EDL" : "Filler restore disabled — re-run EDL");
      await refreshRun();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Could not update filler restore", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="disfluency-restore-panel">
      <p className="hint">
        {confirmedCount} confirmed filler event(s). When enabled, EDL splits speech and inserts disfluency clips at
        source times. Stingers and ambient beds overlapping filler windows may be dropped at mix time.
      </p>
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={enabled}
          disabled={saving}
          onChange={() => void toggle()}
        />
        {saving ? (
          <span className="hint sm">
            <span className="spinner-inline" aria-hidden /> Saving…
          </span>
        ) : (
          "Include confirmed fillers in assembly"
        )}
      </label>
    </div>
  );
}
