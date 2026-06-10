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

  useEffect(() => {
    if (!run) return;
    setEnabled(run.meta?.disfluency_restore?.enabled ?? config?.disfluency_restore_enabled ?? true);
    void api<{ stats?: { confirmed?: number } }>(`/api/runs/${run.run_id}/disfluency-review`)
      .then((data) => setConfirmedCount(data.stats?.confirmed ?? 0))
      .finally(() => setLoading(false));
  }, [run?.run_id, config?.disfluency_restore_enabled, run?.meta?.disfluency_restore?.enabled]);

  if (!config?.disfluency_restore_enabled || loading) return null;
  if (stageId !== "edl_flow1" && stageId !== "assembly_preview") return null;

  const toggle = async () => {
    if (!run) return;
    const next = !enabled;
    await api(`/api/runs/${run.run_id}/disfluency-restore`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: next }),
    });
    setEnabled(next);
    showToast(next ? "Filler restore enabled — re-run EDL" : "Filler restore disabled — re-run EDL");
    await refreshRun();
  };

  return (
    <div className="disfluency-restore-panel">
      <p className="hint">
        {confirmedCount} confirmed filler event(s). When enabled, EDL splits speech and inserts disfluency clips at
        source times.
      </p>
      <label className="toggle-row">
        <input type="checkbox" checked={enabled} onChange={() => void toggle()} />
        Include confirmed fillers in assembly
      </label>
    </div>
  );
}
