import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { shouldBlockOperatorActionsForJob } from "../../utils/partialAcceleratedGuard";
import { GatePanelShell } from "../pipeline/GatePanelShell";

interface OptimizerPayload {
  status?: string;
  running?: boolean;
  generation?: number;
  best_score?: number | null;
  plateau_streak?: number;
  archive_count?: number;
  auto_started?: boolean;
  last_mutation?: { op?: string; score?: number; source?: string } | null;
  best?: {
    candidate_id?: string;
    score?: number;
    ordered_segment_ids?: string[];
    mutations?: unknown[];
  } | null;
}

/** Endless mid-mix timeline optimizer (mode C) — Take best / Keep going / Stop. */
export function TimelineOptimizerPanel() {
  const { runId, run, refreshRun, appendClientLog, showToast, jobRunning, partialAutoGPublish } =
    useApp();
  const [payload, setPayload] = useState<OptimizerPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const jobBlocksUi = shouldBlockOperatorActionsForJob(run, jobRunning, partialAutoGPublish);

  const refresh = async () => {
    if (!runId) return;
    try {
      const res = await api<OptimizerPayload>(`/api/runs/${runId}/timeline-optimizer`);
      setPayload(res);
    } catch {
      setPayload(null);
    }
  };

  useEffect(() => {
    void refresh();
    if (!runId) return;
    const id = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(id);
  }, [runId]);

  if (!runId) return null;
  const active =
    payload?.running ||
    payload?.status === "running" ||
    payload?.status === "stopping" ||
    (payload?.best_score != null && (payload.generation ?? 0) > 0);
  if (!active && !payload?.best) return null;

  const act = async (path: string, label: string, body?: object) => {
    if (jobBlocksUi) {
      showToast("A pipeline job is running — wait until it pauses.", "warning");
      return;
    }
    setBusy(true);
    try {
      await api(`/api/runs/${runId}/timeline-optimizer/${path}`, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      appendClientLog(label, "action", "mix", `gui.timeline_optimizer.${path}`);
      await refreshRun();
      await refresh();
    } catch (err) {
      showToast(String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const mutatorBusy = busy || jobBlocksUi;

  return (
    <GatePanelShell complete={false} title="Timeline optimizer (endless)">
      <p className="hint">
        Per-run search permutes structure, bridges, and sound cues after mix. Daemon keeps going until
        you stop — Take best remasters the current champion.
      </p>
      <p className="hint">
        Status: {payload?.status ?? "—"} · gen {payload?.generation ?? 0} · best{" "}
        {payload?.best_score ?? "—"} · archive {payload?.archive_count ?? 0}
        {payload?.auto_started
          ? " · auto-started after mix (daemon began without a Keep optimizing click)"
          : ""}
        {payload?.last_mutation?.op
          ? ` · last ${payload.last_mutation.op} (${payload.last_mutation.score ?? "—"})`
          : ""}
      </p>
      <div className="gate-actions-row">
        <button
          type="button"
          className="btn sm primary"
          disabled={mutatorBusy || !payload?.best}
          onClick={() => void act("take-best", "Took optimizer best", { remaster: true })}
        >
          Take best + remaster
        </button>
        <button
          type="button"
          className="btn sm ghost"
          disabled={mutatorBusy || payload?.running}
          onClick={() => void act("start", "Started timeline optimizer")}
        >
          Keep optimizing
        </button>
        <button
          type="button"
          className="btn sm ghost"
          disabled={mutatorBusy || !payload?.running}
          onClick={() => void act("stop", "Stopped timeline optimizer")}
        >
          Stop
        </button>
        <button
          type="button"
          className="btn sm ghost"
          disabled={mutatorBusy}
          onClick={() => void act("skip", "Skipped timeline optimizer")}
        >
          Skip / ship current
        </button>
      </div>
    </GatePanelShell>
  );
}
