import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { formatApiError } from "../../utils/safeApi";

type AudioProbesSummary = {
  available: boolean;
  enforcement_mode?: "shadow" | "authoritative" | string;
  run?: {
    has_in_flow_vernacular?: boolean;
    vernacular_flow_count?: number;
    special_keywords?: string[];
  };
  zones_count?: number;
  must_keep_segment_ids?: string[];
  answer_stats?: Record<string, number | string>;
  probe_rows_preview?: Record<string, unknown>[];
  resplit_patterns?: string[];
  artifacts?: string[];
};

export function AudioProbesPanel() {
  const { run, showToast } = useApp();
  const [loading, setLoading] = useState(false);
  const [doc, setDoc] = useState<AudioProbesSummary | null>(null);

  useEffect(() => {
    if (!run) return;
    setLoading(true);
    void api<AudioProbesSummary>(`/api/runs/${run.run_id}/audio-probes`)
      .then((data) => setDoc(data))
      .catch((reason) => {
        setDoc(null);
        showToast(formatApiError(reason, "Audio probes"), "error");
      })
      .finally(() => setLoading(false));
  }, [run, showToast]);

  if (!run) return null;
  if (loading) {
    return (
      <div className="quality-offer-card" data-action-id="gui.audio_probes.view">
        <h4>Audio probes</h4>
        <div className="gate-loading-skeleton panel-inset" aria-busy>
          <span className="spinner-inline" aria-hidden /> Loading audio probes…
        </div>
      </div>
    );
  }
  if (!doc?.available) {
    return (
      <div className="quality-offer-card" data-action-id="gui.audio_probes.view">
        <h4>Audio probes</h4>
        <p className="muted sm">Run audio probes to generate vernacular golden facts.</p>
      </div>
    );
  }

  const vernacular = doc.run?.has_in_flow_vernacular;
  const mustKeepCount = doc.must_keep_segment_ids?.length ?? 0;
  const statsEntries = Object.entries(doc.answer_stats || {}).slice(0, 6);
  const previewRows = (doc.probe_rows_preview || []).slice(0, 6);

  return (
    <div className="quality-offer-card" data-action-id="gui.audio_probes.view">
      <h4>Audio probes</h4>
      <p className="muted sm">
        Vernacular: <strong>{vernacular ? "yes" : "no"}</strong>
        {doc.run?.vernacular_flow_count != null
          ? ` (${doc.run.vernacular_flow_count} flow${doc.run.vernacular_flow_count === 1 ? "" : "s"})`
          : ""}
        · mode <strong>{doc.enforcement_mode || "shadow"}</strong>
      </p>
      <p className="muted sm">
        Zones <strong>{doc.zones_count ?? 0}</strong> · must-keep{" "}
        <strong>{mustKeepCount}</strong>
        {doc.resplit_patterns?.length
          ? ` · patterns ${doc.resplit_patterns.slice(0, 4).join(", ")}`
          : ""}
      </p>
      {statsEntries.length ? (
        <p className="muted sm">
          Answer stats:{" "}
          {statsEntries.map(([k, v]) => `${k}=${v}`).join(" · ")}
        </p>
      ) : null}
      {previewRows.length ? (
        <table className="placement-qa-table">
          <thead>
            <tr>
              <th>Probe</th>
              <th>Answer</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {previewRows.map((row, i) => (
              <tr key={`${String(row.probe_id || "row")}-${i}`}>
                <td>
                  <code>{String(row.probe_id || "—")}</code>
                </td>
                <td className="muted sm">
                  {row.skipped
                    ? `skipped${row.skip_reason ? `: ${String(row.skip_reason)}` : ""}`
                    : (() => {
                        const parsed = row.parsed as { value?: unknown } | undefined;
                        const ans = row.answer as { text?: unknown } | undefined;
                        const text =
                          parsed?.value != null
                            ? String(parsed.value)
                            : ans?.text != null
                              ? String(ans.text)
                              : "—";
                        return text.slice(0, 80);
                      })()}
                </td>
                <td className="muted sm">{String(row.answer_source || "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
