import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { StageInfo } from "../../types";
import { formatApiError } from "../../utils/safeApi";

interface GapLine {
  line_id: string;
  text?: string;
  line_category?: string;
  gap_type?: string;
  targets_segment_id?: string;
  placement?: string;
  supports_segment_ids?: string[];
  replaces_source_segments?: string[];
  delivery?: string;
  nugget_ids?: string[];
  skipped_optional?: boolean;
}

interface OmitEntry {
  entry_id?: string;
  subject_id?: string;
  target_segment_id?: string | null;
  decision?: string;
  reason_code?: string;
  compensating_path?: string | null;
  value_forgone?: string[];
  active?: boolean;
}

interface GapFramingScriptPayload {
  lines?: GapLine[];
  plan?: { acts?: unknown[] } | null;
  omit_ledger?: { entries?: OmitEntry[] };
  omit_summary?: {
    active_count?: number;
    compensated_count?: number;
    unresolved_high_salience?: number;
  };
}

const CATEGORY_LABEL: Record<string, string> = {
  episode_preface: "Preface",
  segment_summary: "Summary",
  story_bridge: "Bridge",
  framing_question: "Question",
  context_setup: "Setup",
  extracted_context: "Context",
};

export function GapFramingScriptPanel({ stage }: { stage: StageInfo }) {
  const { runId, showToast } = useApp();
  const [data, setData] = useState<GapFramingScriptPayload | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!runId) return;
    try {
      const res = await api<GapFramingScriptPayload>(`/api/runs/${runId}/gap-framing/script`);
      setData(res);
    } catch (e) {
      showToast(formatApiError(e, "Load framing script"), "error");
    }
  }, [runId, showToast]);

  useEffect(() => {
    void load();
  }, [load, stage.status]);

  const saveLine = async (lineId: string, text: string) => {
    if (!runId || busyId) return;
    setBusyId(lineId);
    try {
      await api(`/api/runs/${runId}/gap-report/lines/${lineId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      showToast(`Saved ${lineId}`);
      await load();
    } catch (e) {
      showToast(formatApiError(e, "Save line"), "error");
    } finally {
      setBusyId(null);
    }
  };

  const lines = data?.lines || [];
  const omitByTarget = new Map<string, OmitEntry>();
  for (const entry of data?.omit_ledger?.entries || []) {
    if (!entry?.active) continue;
    const tid = String(entry.target_segment_id || entry.subject_id || "");
    if (tid) omitByTarget.set(tid, entry);
  }
  if (!lines.length) {
    return (
      <p className="hint sm" data-testid="gap-framing-script-panel">
        No framing lines yet — run gap framing compose first.
      </p>
    );
  }

  return (
    <section className="gap-framing-script-panel panel-inset" data-testid="gap-framing-script-panel">
      <h4>Framing script</h4>
      <p className="hint sm">
        Edit interviewer copy before G1. Categories control word budgets and sound-design cues.
        {data?.omit_summary?.active_count
          ? ` · ${data.omit_summary.active_count} omit decision(s)`
          : ""}
      </p>
      <ul className="pickup-speaker-list">
        {lines.map((line) => {
          const cat = line.line_category || line.gap_type || "line";
          const label = CATEGORY_LABEL[cat] || cat;
          const omit = omitByTarget.get(String(line.targets_segment_id || line.line_id || ""));
          return (
            <li key={line.line_id} className="pickup-speaker-card vo-card">
              <div className="vo-card-head">
                <strong>{line.line_id}</strong>
                <span className="badge sm">{label}</span>
                {line.skipped_optional ? <span className="badge sm">skipped</span> : null}
                {omit ? <span className="badge sm">{omit.decision || "omit"}</span> : null}
                <span className="muted sm">
                  → {line.targets_segment_id} ({line.placement || "before"})
                </span>
              </div>
              <textarea
                className="input-block"
                defaultValue={line.text || ""}
                rows={3}
                disabled={busyId === line.line_id}
                onBlur={(e) => {
                  const next = e.target.value.trim();
                  if (next && next !== (line.text || "").trim()) {
                    void saveLine(line.line_id, next);
                  }
                }}
              />
              {line.nugget_ids?.length ? (
                <p className="hint sm">Nuggets: {line.nugget_ids.join(", ")}</p>
              ) : null}
              {omit?.compensating_path ? (
                <p className="hint sm">
                  Omit path: {omit.reason_code} → {omit.compensating_path}
                </p>
              ) : null}
              {line.supports_segment_ids?.length ? (
                <p className="hint sm">Supports: {line.supports_segment_ids.join(", ")}</p>
              ) : null}
              {line.replaces_source_segments?.length ? (
                <p className="hint sm">Replaces: {line.replaces_source_segments.join(", ")}</p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
