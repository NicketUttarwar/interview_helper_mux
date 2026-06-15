import { useCallback, useEffect, useState } from "react";
import { useApp } from "../../context/AppContext";
import { api } from "../../api/client";
import type { AnalysisState, StoryBoardData } from "../../types";
import {
  collectAnalysisProfileFromForm,
  loadProfileToForm,
  type ProfileFormState,
} from "./profileForm";
import {
  TONE_CLASS_VALUES,
  formatClassLabel,
} from "../../utils/toneTaxonomy";
import { ActionMarker } from "../guidance/ActionMarker";

function investigationItems(queue: Record<string, unknown>): Array<Record<string, unknown>> {
  const items = queue.items ?? queue.investigations;
  return Array.isArray(items) ? (items as Array<Record<string, unknown>>) : [];
}

export function StoryBoardPanel() {
  const { runId, run, refreshRun, config, setPipelineSubTab } = useApp();
  const [data, setData] = useState<StoryBoardData | null>(null);
  const [form, setForm] = useState<ProfileFormState | null>(null);
  const [baseState, setBaseState] = useState<AnalysisState | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    const sb = await api<StoryBoardData>(`/api/runs/${runId}/story-board`);
    setData(sb);
    setBaseState(sb.analysis_state);
    setForm(loadProfileToForm(sb.analysis_state));
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (verify?: boolean) => {
    if (!runId || !form) return;
    setSaving(true);
    try {
      if (verify) {
        await api(`/api/runs/${runId}/analysis-profile/verify`, { method: "POST" });
      }
      await api(`/api/runs/${runId}/analysis-profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data: collectAnalysisProfileFromForm(form, baseState),
        }),
      });
      await load();
      await refreshRun();
    } finally {
      setSaving(false);
    }
  };

  const resolveInvestigation = async (itemId: string) => {
    if (!runId) return;
    await api(`/api/runs/${runId}/investigation-queue/${itemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "resolved" }),
    });
    await load();
    await refreshRun();
  };

  if (!data || !form) {
    return (
      <div className="story-board panel">
        <h3>Story Board</h3>
        <ul className="stage-guidance-list">
          <li className="stage-guidance-item status-todo">
            <ActionMarker status="todo" />
            <span className="stage-guidance-label">
              Unlocks after content understanding — run Analyze phase stages first
            </span>
          </li>
        </ul>
      </div>
    );
  }

  const openItems = investigationItems(data.investigation_queue).filter(
    (it) => (it.status as string) !== "resolved",
  );
  const brief = data.content_brief as { one_line_summary?: string };
  const sap = data.source_acoustic_profile as Record<string, string> | null;

  return (
    <div className="story-board panel">
      <h3>Story Board</h3>
      <p className="story-headline">{form.title || brief.one_line_summary || "Untitled interview"}</p>
      <label className="field">
        Thesis / summary
        <textarea
          value={form.summary}
          onChange={(e) => setForm({ ...form, summary: e.target.value })}
          rows={2}
        />
      </label>
      <label className="field">
        Tone class
        <select
          value={form.toneClass}
          onChange={(e) => setForm({ ...form, toneClass: e.target.value })}
        >
          <option value="">— Select —</option>
          {TONE_CLASS_VALUES.map((v) => (
            <option key={v} value={v}>
              {formatClassLabel(v)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Tone (nuance)
        <input value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })} />
      </label>
      {form.formatClass ? (
        <p className="muted">
          Format: {formatClassLabel(form.formatClass)}
          {form.formatNotes ? ` — ${form.formatNotes}` : ""}
        </p>
      ) : null}
      {openItems.length > 0 ? (
        <section>
          <h4>Open questions ({openItems.length})</h4>
          <ul>
            {openItems.map((it) => (
              <li key={String(it.id)}>
                {String(it.question ?? it.summary ?? it.kind ?? it.id)}
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => void resolveInvestigation(String(it.id))}
                >
                  Resolve
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {sap ? (
        <p className="sap-strip">
          Sonic profile: {sap.pace_class ?? "—"} · beds {sap.bed_density ?? "—"} · stingers{" "}
          {sap.stinger_policy ?? "—"}
        </p>
      ) : null}
      {(run?.journey?.sound_labels || []).length ? (
        <p className="muted sm">
          Sound labels:{" "}
          {(run?.journey?.sound_labels || []).map((label) => (
            <span key={label} className="badge" style={{ marginRight: "0.35rem" }}>
              {label}
            </span>
          ))}
        </p>
      ) : null}
      {config?.value_analysis_enabled && data.value_features ? (
        <p className="muted">Research metrics (advisory only) — see value_features.json</p>
      ) : null}
      <div className="story-actions">
        <button type="button" className="btn" disabled={saving} onClick={() => void save(false)}>
          Save story
        </button>
        <button type="button" className="btn primary" disabled={saving} onClick={() => void save(true)}>
          Lock story for podcast edit
        </button>
        <button type="button" className="btn ghost" onClick={() => setPipelineSubTab("timeline")}>
          Edit timeline
        </button>
      </div>
    </div>
  );
}
