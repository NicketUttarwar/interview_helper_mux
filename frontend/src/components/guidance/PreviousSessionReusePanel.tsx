import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";

interface LineageStage {
  stage_id: string;
  title: string;
  eligible: boolean;
  previous_done: boolean;
  source_run_id?: string;
}

interface LineageResponse {
  immediate_previous_run_id?: string | null;
  recent_prior_run_ids?: string[];
  hash_match_with_previous?: boolean;
  previous_run_summary?: { run_id: string; execution_number?: number };
  stages: LineageStage[];
}

interface Props {
  /** When set, only show reuse for this pipeline stage (never as a global banner). */
  stageId: string;
  compact?: boolean;
}

export function PreviousSessionReusePanel({ stageId, compact = false }: Props) {
  const { runId, run, refreshRun, showToast, config } = useApp();
  const reuseOffersEnabled = config?.journey_ui?.enable_stage_reuse_offers !== false;
  const [lineage, setLineage] = useState<LineageResponse | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!reuseOffersEnabled) {
      setLineage(null);
      return;
    }
    try {
      const data = await api<LineageResponse>("/api/session/lineage");
      setLineage(data);
    } catch {
      setLineage(null);
    }
  }, [reuseOffersEnabled]);

  useEffect(() => {
    void load();
  }, [load, runId]);

  if (!reuseOffersEnabled) return null;

  if (!lineage?.hash_match_with_previous) return null;
  if (run?.meta?.stage_reuse?.[stageId]?.action) return null;

  const stageEntry = lineage.stages.find((s) => s.stage_id === stageId);
  if (!stageEntry?.eligible) return null;

  const sourceRunId =
    stageEntry.source_run_id ??
    lineage.previous_run_summary?.run_id ??
    lineage.recent_prior_run_ids?.[0] ??
    lineage.immediate_previous_run_id ??
    "prior execution";

  const bulkReuse = async () => {
    if (!runId || busy) return;
    setBusy(true);
    showToast("Copying eligible stages from previous execution…");
    try {
      await api(`/api/runs/${runId}/reuse-from-previous`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage_ids: [stageId] }),
      });
      showToast(`Copied ${stageEntry?.title ?? stageId} from previous execution.`);
      await refreshRun();
      await load();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Bulk reuse failed", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`previous-session-reuse panel${compact ? " compact" : ""}`}>
      <h3 className={compact ? "hint" : undefined}>Previous session</h3>
      <p className="hint sm">
        {sourceRunId}
        {lineage.hash_match_with_previous ? " — same source audio" : " — different source audio"}
      </p>
      {!lineage.hash_match_with_previous ? (
        <p className="hint sm">Reuse unavailable (hash mismatch).</p>
      ) : (
        <>
          <p className="hint sm">
            {stageEntry.title} outputs are available from {sourceRunId}.
          </p>
          <button type="button" className="btn primary sm" disabled={busy} onClick={() => void bulkReuse()}>
            {busy ? (
              <>
                <span className="spinner-inline" aria-hidden /> Copying…
              </>
            ) : (
              `Reuse ${stageEntry.title} from previous session`
            )}
          </button>
        </>
      )}
    </div>
  );
}
