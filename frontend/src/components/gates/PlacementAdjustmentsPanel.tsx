import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { escapeHtml } from "../../utils";
import type { StageInfo } from "../../types";

type PlacementAdjustment = {
  asset_id?: string;
  action?: string;
  reason?: string;
  mmaudio_qa_verdict?: string;
  suggested_level_db_delta?: number;
  suggested_crossfade_ms?: number;
  suggested_trim_ms?: number;
  provenance?: {
    rule_id?: string;
    source_artifact?: string;
    detail?: string;
  };
  scenario_override?: boolean;
};

const PLACEMENT_STAGES = new Set([
  "mix_flow1",
  "mix_flow2",
  "mmaudio_sfx_flow1",
  "mmaudio_sfx_flow2",
]);

export function PlacementAdjustmentsPanel({ stage }: { stage: StageInfo }) {
  const { run, appendClientLog } = useApp();
  const [adjustments, setAdjustments] = useState<PlacementAdjustment[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!run || !PLACEMENT_STAGES.has(stage.id)) {
      setAdjustments([]);
      return;
    }
    setLoading(true);
    void api<{ adjustments?: PlacementAdjustment[]; version?: number }>(
      `/api/runs/${run.run_id}/artifact?path=${encodeURIComponent("sound_design/placement_adjustments.json")}`,
    )
      .then((data) => setAdjustments(Array.isArray(data.adjustments) ? data.adjustments : []))
      .catch((e) => {
        setAdjustments([]);
        appendClientLog(
          e instanceof Error ? e.message : "Failed to load placement adjustments",
          "warning",
        );
      })
      .finally(() => setLoading(false));
  }, [run, stage.id, appendClientLog]);

  if (!run || !PLACEMENT_STAGES.has(stage.id)) return null;
  if (loading) {
    return (
      <div className="placement-qa-card quality-offer-card">
        <h4>Placement QA</h4>
        <div className="gate-loading-skeleton panel-inset" aria-busy>
          <span className="spinner-inline" aria-hidden /> Loading placement adjustments…
        </div>
      </div>
    );
  }
  if (!adjustments.length) return null;
  const hasProvenance = adjustments.some((row) => Boolean(row.provenance));
  const hasScenarioOverride = adjustments.some(
    (row) => row.scenario_override !== undefined,
  );

  return (
    <div className="quality-offer-card placement-qa-card">
      <h4>Placement QA adjustments</h4>
      <p className="muted sm">
        Hints from <code>sound_design/placement_adjustments.json</code> applied at mix time.
      </p>
      <table className="placement-qa-table">
        <thead>
          <tr>
            <th>Asset</th>
            <th>QA</th>
            <th>Action</th>
            <th>Level Δ</th>
            <th>Crossfade</th>
            {hasProvenance ? <th>Provenance</th> : null}
            {hasScenarioOverride ? <th>Scenario override</th> : null}
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {adjustments.map((row, i) => (
            <tr key={i}>
              <td>
                <code>{escapeHtml(row.asset_id || "—")}</code>
              </td>
              <td>
                {row.mmaudio_qa_verdict
                  ? escapeHtml(row.mmaudio_qa_verdict)
                  : "—"}
              </td>
              <td>{escapeHtml(row.action || "—")}</td>
              <td>
                {row.suggested_level_db_delta != null
                  ? `${row.suggested_level_db_delta} dB`
                  : "—"}
              </td>
              <td>
                {row.suggested_crossfade_ms != null ? `${row.suggested_crossfade_ms} ms` : "—"}
              </td>
              {hasProvenance ? (
                <td className="muted sm">
                  {row.provenance
                    ? [
                        row.provenance.rule_id,
                        row.provenance.source_artifact,
                        row.provenance.detail,
                      ]
                        .filter(Boolean)
                        .join(" · ")
                    : "—"}
                </td>
              ) : null}
              {hasScenarioOverride ? (
                <td>{row.scenario_override == null ? "—" : row.scenario_override ? "yes" : "no"}</td>
              ) : null}
              <td className="muted sm">{escapeHtml(row.reason || "—")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
