import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { escapeHtml } from "../../utils";
import type { StageInfo } from "../../types";

type PlacementAdjustment = {
  asset_id?: string;
  action?: string;
  reason?: string;
  suggested_level_db_delta?: number;
  suggested_crossfade_ms?: number;
};

const PLACEMENT_STAGES = new Set([
  "mix_flow1",
  "mix_flow2",
  "elevenlabs_sfx_flow1",
  "elevenlabs_sfx_flow2",
]);

export function PlacementAdjustmentsPanel({ stage }: { stage: StageInfo }) {
  const { run } = useApp();
  const [adjustments, setAdjustments] = useState<PlacementAdjustment[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!run || !PLACEMENT_STAGES.has(stage.id)) {
      setAdjustments([]);
      return;
    }
    setLoading(true);
    void api<{ content?: { adjustments?: PlacementAdjustment[] } }>(
      `/api/runs/${run.run_id}/artifact?path=${encodeURIComponent("sound_design/placement_adjustments.json")}`,
    )
      .then((data) => setAdjustments(data.content?.adjustments || []))
      .catch(() => setAdjustments([]))
      .finally(() => setLoading(false));
  }, [run, stage.id]);

  if (!run || !PLACEMENT_STAGES.has(stage.id)) return null;
  if (loading) {
    return (
      <div className="quality-offer-card placement-qa-card">
        <h4>Placement QA</h4>
        <p className="muted sm">Loading placement adjustments…</p>
      </div>
    );
  }
  if (!adjustments.length) return null;

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
            <th>Action</th>
            <th>Level Δ</th>
            <th>Crossfade</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {adjustments.map((row, i) => (
            <tr key={i}>
              <td>
                <code>{escapeHtml(row.asset_id || "—")}</code>
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
              <td className="muted sm">{escapeHtml(row.reason || "—")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
