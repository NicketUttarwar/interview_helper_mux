import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";

interface LineageStage {
  stage_id: string;
  title: string;
  eligible: boolean;
  previous_done: boolean;
}

interface LineageResponse {
  immediate_previous_run_id?: string | null;
  hash_match_with_previous?: boolean;
  previous_run_summary?: { run_id: string; execution_number?: number };
  stages: LineageStage[];
}

export function PreviousSessionReusePanel({ compact = false }: { compact?: boolean }) {
  const { runId, refreshRun, showToast } = useApp();
  const [lineage, setLineage] = useState<LineageResponse | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api<LineageResponse>("/api/session/lineage");
      setLineage(data);
    } catch {
      setLineage(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, runId]);

  if (!lineage?.immediate_previous_run_id) return null;
  const eligible = lineage.stages.filter((s) => s.eligible);
  if (!eligible.length && compact) return null;

  const bulkReuse = async () => {
    if (!runId || busy) return;
    setBusy(true);
    showToast("Copying eligible stages from previous execution…");
    try {
      await api(`/api/runs/${runId}/reuse-from-previous`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accept_all: true }),
      });
      showToast("Copied eligible stages from previous execution.");
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
        {lineage.previous_run_summary?.run_id}
        {lineage.hash_match_with_previous ? " — same source audio" : " — different source audio"}
      </p>
      {!lineage.hash_match_with_previous ? (
        <p className="hint sm">Reuse unavailable (hash mismatch).</p>
      ) : eligible.length ? (
        <>
          <p className="hint sm">{eligible.length} stage(s) can copy outputs.</p>
          <button type="button" className="btn primary sm" disabled={busy} onClick={() => void bulkReuse()}>
            {busy ? (
              <>
                <span className="spinner-inline" aria-hidden /> Copying…
              </>
            ) : (
              "Copy all eligible outputs"
            )}
          </button>
        </>
      ) : (
        <p className="hint sm">No reusable stages from immediate previous execution.</p>
      )}
    </div>
  );
}
