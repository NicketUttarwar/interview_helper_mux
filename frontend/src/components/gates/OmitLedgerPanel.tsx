import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatApiError } from "../../utils/safeApi";

interface OmitEntry {
  entry_id: string;
  kind?: string;
  subject_id?: string;
  target_segment_id?: string | null;
  decision?: string;
  reason_code?: string;
  rationale?: string | null;
  evidence_refs?: string[];
  value_forgone?: string[];
  compensating_path?: string | null;
  revisit_if?: string[];
  decision_confidence?: number | null;
  owner_stage?: string;
  operator_override?: boolean;
  active?: boolean;
}

interface OmitLedgerPayload {
  summary?: {
    active_count?: number;
    compensated_count?: number;
    unresolved_high_salience?: number;
    by_kind?: Record<string, number>;
  };
  active_entries?: OmitEntry[];
}

export function OmitLedgerPanel({ stageId }: { stageId?: string }) {
  const { runId, showToast } = useApp();
  const [data, setData] = useState<OmitLedgerPayload | null>(null);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await api<OmitLedgerPayload>(`/api/runs/${runId}/omit-ledger`);
      setData(res);
    } catch (e) {
      showToast(formatApiError(e, "Load omit ledger"), "error");
    }
  }, [runId, showToast]);

  useEffect(() => {
    void load();
  }, [load, stageId]);

  const entries = data?.active_entries || [];
  const summary = data?.summary || {};

  if (!entries.length) {
    return (
      <p className="hint sm" data-testid="omit-ledger-panel">
        No omit entries — every kept native either has a lay-up or has not been decided yet.
      </p>
    );
  }

  return (
    <section className="omit-ledger-panel panel-inset" data-testid="omit-ledger-panel">
      <h4>Omit decisions</h4>
      <p className="hint sm">
        Active skips and suppresses with evidence and compensating paths.{" "}
        {summary.active_count ?? entries.length} active
        {summary.compensated_count != null ? ` · ${summary.compensated_count} compensated` : ""}
        {summary.unresolved_high_salience
          ? ` · ${summary.unresolved_high_salience} unresolved high-salience`
          : ""}
      </p>
      <ul className="pickup-speaker-list">
        {entries.map((entry) => (
          <li key={entry.entry_id} className="pickup-speaker-card vo-card">
            <div className="vo-card-head">
              <strong>{entry.subject_id || entry.entry_id}</strong>
              <span className="badge sm">{entry.decision || entry.kind || "omit"}</span>
              {entry.operator_override ? <span className="badge sm">operator</span> : null}
            </div>
            <p className="hint sm">
              {entry.reason_code || "unspecified"}
              {entry.target_segment_id ? ` → ${entry.target_segment_id}` : ""}
              {entry.owner_stage ? ` · ${entry.owner_stage}` : ""}
            </p>
            {entry.rationale ? <p className="sm">{entry.rationale}</p> : null}
            {entry.compensating_path ? (
              <p className="hint sm">Compensating: {entry.compensating_path}</p>
            ) : (
              <p className="hint sm">No compensating path</p>
            )}
            {entry.value_forgone?.length ? (
              <p className="hint sm">Value forgone: {entry.value_forgone.join(", ")}</p>
            ) : null}
            {entry.evidence_refs?.length ? (
              <p className="hint sm">Evidence: {entry.evidence_refs.slice(0, 4).join(", ")}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
