import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { COHERENCE_REPORT_PATH } from "../../utils";
import {
  formatApiError,
  isExpectedEmptyApiError,
  reportPanelFetchOutcome,
} from "../../utils/safeApi";
import type { CoherenceReport, CoherenceRisk } from "../../types";
import { GatePanelShell } from "../pipeline/GatePanelShell";

export function CoherenceRisksPanel() {
  const { run, refreshRun, showToast, appendClientLog, confirm } = useApp();
  const [report, setReport] = useState<CoherenceReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!run) return;
    setLoadError(null);
    try {
      const data = await api<CoherenceReport>(`/api/runs/${run.run_id}/coherence-report`);
      setReport(data);
    } catch (e) {
      if (isExpectedEmptyApiError(e)) {
        setReport(null);
        setLoadError(null);
        return;
      }
      setReport(null);
      const msg = reportPanelFetchOutcome({
        error: e,
        kind: "system",
        label: "Coherence report",
        appendClientLog,
        showToast,
      });
      setLoadError(msg);
    } finally {
      setInitialLoading(false);
    }
  }, [run, appendClientLog, showToast]);

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
    } catch (e) {
      reportPanelFetchOutcome({
        error: e,
        kind: "action_failed",
        label: "Recompute coherence",
        appendClientLog,
        showToast,
      });
    } finally {
      setLoading(false);
    }
  };

  if (initialLoading && !report && !loadError) {
    return (
      <section className="coherence-risks-card quality-offer-card">
        <h4>Long-run coherence</h4>
        <div className="gate-loading-skeleton panel-inset" aria-busy>
          <span className="spinner-inline" aria-hidden /> Loading coherence report…
        </div>
      </section>
    );
  }

  if (loadError && !report) {
    return (
      <section className="coherence-risks-card quality-offer-card">
        <h4>Long-run coherence</h4>
        <p className="error-text" role="alert">
          {loadError}
        </p>
        <button type="button" className="btn ghost sm" onClick={() => void load()}>
          Retry
        </button>
      </section>
    );
  }

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
  const risksClosed = openRisks.length === 0;

  return (
    <GatePanelShell
      complete={risksClosed}
      title="Coherence review complete — no open risks"
      className="coherence-risks-card quality-offer-card"
    >
      <div className="coherence-risks-header">
        <h4>Coherence risks</h4>
        <button type="button" className="btn ghost sm" disabled={loading} onClick={() => void recompute()}>
          {loading ? (
            <>
              <span className="spinner-inline" aria-hidden /> Recomputing…
            </>
          ) : (
            "Recompute"
          )}
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
        <>
          {openRisks.some((r) => r.blocking) ? (
            <p className="hint sm">
              Blocking risks must be resolved on the Story Board before profile verification.
            </p>
          ) : null}
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
        </>
      )}
      <p className="muted sm">Artifact: {COHERENCE_REPORT_PATH}</p>
    </GatePanelShell>
  );
}
