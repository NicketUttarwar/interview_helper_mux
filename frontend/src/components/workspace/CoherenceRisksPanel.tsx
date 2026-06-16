import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { COHERENCE_REPORT_PATH } from "../../utils";
import type { CoherenceReport, CoherenceRisk } from "../../types";

export function CoherenceRisksPanel() {
  const { run, refreshRun, showToast, confirm } = useApp();
  const [report, setReport] = useState<CoherenceReport | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!run) return;
    try {
      const data = await api<CoherenceReport>(`/api/runs/${run.run_id}/coherence-report`);
      setReport(data);
    } catch {
      setReport(null);
    }
  }, [run]);

  useEffect(() => {
    void load();
  }, [load]);

  const recompute = async () => {
    if (!run) return;
    if (!(await confirm("Recompute coherence report from spine + content brief?"))) return;
    setLoading(true);
    try {
      await api(`/api/runs/${run.run_id}/recompute-coherence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phase: "post_reanchor" }),
      });
      showToast("Coherence report recomputed.");
      await refreshRun();
      await load();
    } finally {
      setLoading(false);
    }
  };

  if (!report?.gate?.activated) {
    return (
      <section className="coherence-risks-card quality-offer-card">
        <h4>Long-run coherence</h4>
        <p className="hint">
          H-ORC-03 activates on interviews ≥ 30 minutes. Current duration:{" "}
          {report?.gate?.duration_ms
            ? `${Math.round(report.gate.duration_ms / 60000)}m`
            : "unknown"}
          .
        </p>
      </section>
    );
  }

  const openRisks = (report.risks || []).filter((r) => r.status !== "resolved");
  const summary = report.summary;

  return (
    <section className="coherence-risks-card quality-offer-card">
      <div className="coherence-risks-header">
        <h4>Coherence risks</h4>
        <button type="button" className="btn ghost sm" disabled={loading} onClick={() => void recompute()}>
          Recompute
        </button>
      </div>
      <p className="muted sm">
        Drift {summary?.topic_drift_count ?? 0} · Contradictions{" "}
        {summary?.claim_contradiction_count ?? 0} · Missing callbacks{" "}
        {summary?.missing_callback_count ?? 0}
      </p>
      {openRisks.length === 0 ? (
        <p className="hint">No open coherence risks.</p>
      ) : (
        <ul className="coherence-risk-list">
          {openRisks.map((risk: CoherenceRisk) => (
            <li key={risk.risk_id} className={risk.blocking ? "coherence-risk blocking" : "coherence-risk"}>
              <span className="coherence-risk-kind">{risk.kind}</span>
              <span className="coherence-risk-time">
                {risk.time_ms != null ? `${Math.floor(risk.time_ms / 60000)}:${String(Math.floor((risk.time_ms % 60000) / 1000)).padStart(2, "0")}` : "—"}
              </span>
              <span className="coherence-risk-confidence">{Math.round((risk.confidence ?? 0) * 100)}%</span>
              {risk.blocking ? <span className="badge warn">blocking</span> : null}
            </li>
          ))}
        </ul>
      )}
      <p className="muted sm">Artifact: {COHERENCE_REPORT_PATH}</p>
    </section>
  );
}
