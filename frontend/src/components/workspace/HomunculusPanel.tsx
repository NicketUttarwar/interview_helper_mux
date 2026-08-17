import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";

interface HomunculusStatus {
  homunculus_version?: string;
  active?: boolean;
  budget?: {
    remaining?: Record<string, number>;
    max_invokes_per_identity?: number;
    max_conductor_turns?: number;
  };
  last_fact_ids?: string[];
  admitted_tail?: Array<{ fact_id?: string; action?: string; identity?: string }>;
  issues?: Array<{ issue_id?: string; kind?: string }>;
  limit_exhausted?: { identity?: string; reason?: string } | null;
  memory_fact_count?: number;
}

export function HomunculusPanel() {
  const { runId, run } = useApp();
  const version = run?.meta?.homunculus_version || "0.0.0";
  const [status, setStatus] = useState<HomunculusStatus | null>(null);

  useEffect(() => {
    if (!runId || version !== "0.1.0") {
      setStatus(null);
      return;
    }
    let cancelled = false;
    void api<HomunculusStatus>(`/api/runs/${runId}/homunculus`)
      .then((data) => {
        if (!cancelled) setStatus(data);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, version, run?.meta?.updated_at]);

  if (version !== "0.1.0") return null;

  const remaining = status?.budget?.remaining || {};
  const lastIds = status?.last_fact_ids || [];
  const admitted = status?.admitted_tail || [];
  const omitted = admitted
    .map((row) => row.fact_id)
    .filter((id): id is string => Boolean(id) && !lastIds.includes(id));

  return (
    <section className="panel panel-compact" data-testid="homunculus-panel">
      <div className="panel-head">
        <h3>Why this volley</h3>
      </div>
      {status?.limit_exhausted ? (
        <p className="hint" role="alert">
          Limit exhausted: {status.limit_exhausted.identity} ({status.limit_exhausted.reason})
        </p>
      ) : null}
      <p className="hint sm">
        Remaining 3/1 caps shown per identity. Packer selects fact IDs; host renders turns.
      </p>
      <div className="asset-meta">
        Selected facts: {lastIds.length ? lastIds.join(", ") : "(none yet)"}
      </div>
      <div className="asset-meta">
        Omitted but available: {omitted.length ? omitted.slice(0, 8).join(", ") : "(none)"}
      </div>
      <div className="asset-meta">
        Memory facts: {status?.memory_fact_count ?? 0}
        {Object.keys(remaining).length
          ? ` · remaining: ${Object.entries(remaining)
              .slice(0, 6)
              .map(([k, v]) => `${k}:${v}`)
              .join(" ")}`
          : ""}
      </div>
    </section>
  );
}
