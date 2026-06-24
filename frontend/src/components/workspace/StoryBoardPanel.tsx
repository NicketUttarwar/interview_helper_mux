import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { formatApiError, reportPanelFetchOutcome } from "../../utils/safeApi";
import { completeAnalysisProfile } from "../../utils/analysisProfileCheckpoint";
import { ActionMarker } from "../guidance/ActionMarker";
import { CoherenceRisksPanel } from "./CoherenceRisksPanel";
import { GatePanelShell } from "../pipeline/GatePanelShell";

function investigationItems(queue: Record<string, unknown>): Array<Record<string, unknown>> {
  const items = queue.items ?? queue.investigations;
  return Array.isArray(items) ? (items as Array<Record<string, unknown>>) : [];
}

export function StoryBoardPanel() {
  const { runId, run, refreshRun, config, setPipelineSubTab, showToast, appendClientLog, advanceFromCheckpoint, setCheckpointBusy } = useApp();
  const [data, setData] = useState<StoryBoardData | null>(null);
  const [form, setForm] = useState<ProfileFormState | null>(null);
  const [baseState, setBaseState] = useState<AnalysisState | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const loadErrorLoggedRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (!runId) return;
    setLoadError(null);
    setLoading(true);
    try {
      const sb = await api<StoryBoardData>(`/api/runs/${runId}/story-board`);
      setData(sb);
      setBaseState(sb.analysis_state);
      setForm(loadProfileToForm(sb.analysis_state));
      loadErrorLoggedRef.current = null;
    } catch (e) {
      setData(null);
      setForm(null);
      const msg = formatApiError(e, "Story board");
      setLoadError(msg);
      showToast(msg, "error");
      if (loadErrorLoggedRef.current !== msg) {
        loadErrorLoggedRef.current = msg;
        reportPanelFetchOutcome({
          error: e,
          kind: "system",
          label: "Story board",
          appendClientLog,
        });
      }
    } finally {
      setLoading(false);
    }
  }, [runId, showToast, appendClientLog]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (verify?: boolean) => {
    if (!runId || !form || !baseState || saving) return;
    setSaving(true);
    try {
      const data = collectAnalysisProfileFromForm(form, baseState);
      await completeAnalysisProfile({
        runId,
        data,
        verify: Boolean(verify),
        refreshRun,
        advanceFromCheckpoint,
        showToast,
        appendClientLog,
        setBusy: setCheckpointBusy,
        successMessage: verify
          ? "Story locked and profile verified — continuing pipeline."
          : undefined,
      });
      await load();
    } catch (e) {
      const msg = formatApiError(e, verify ? "Lock story" : "Save story");
      if (!verify) {
        showToast(msg, "error");
        appendClientLog(msg, "error");
      }
    } finally {
      setSaving(false);
    }
  };

  const resolveInvestigation = async (itemId: string) => {
    if (!runId || resolvingId) return;
    setResolvingId(itemId);
    showToast("Resolving investigation…");
    try {
      await api(`/api/runs/${runId}/investigation-queue/${itemId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "resolved" }),
      });
      showToast("Investigation resolved.");
      await load();
      await refreshRun();
    } catch (e) {
      const msg = formatApiError(e, "Resolve investigation");
      showToast(msg, "error");
      appendClientLog(msg, "error");
    } finally {
      setResolvingId(null);
    }
  };

  const openItems = useMemo(
    () =>
      data
        ? investigationItems(data.investigation_queue).filter(
            (it) => (it.status as string) !== "resolved",
          )
        : [],
    [data],
  );

  const profileVerified =
    run?.stages.find((s) => s.id === "analysis_profile")?.status === "done";
  const storyComplete = Boolean(data && openItems.length === 0 && profileVerified);

  if (loadError) {
    return (
      <div className="story-board panel">
        <h3>Story Board</h3>
        <p className="error-text" role="alert">
          {loadError}
        </p>
        <button type="button" className="btn ghost sm" onClick={() => void load()}>
          Retry
        </button>
      </div>
    );
  }

  if (!data || !form) {
    if (loading) {
      return (
        <div className="story-board panel">
          <h3>Story Board</h3>
          <div className="gate-loading-skeleton panel-inset" aria-busy>
            <span className="spinner-inline" aria-hidden /> Loading story board…
          </div>
        </div>
      );
    }
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

  const brief = data.content_brief as { one_line_summary?: string };
  const sap = data.source_acoustic_profile as Record<string, string> | null;

  const body = (
    <>
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
                  disabled={resolvingId !== null}
                  onClick={() => void resolveInvestigation(String(it.id))}
                >
                  {resolvingId === String(it.id) ? (
                    <>
                      <span className="spinner-inline" aria-hidden /> Resolving…
                    </>
                  ) : (
                    "Resolve"
                  )}
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
      {data.interview_spine ? (
        <p className="muted sm">
          Spine: {Array.isArray((data.interview_spine as { windows?: unknown[] }).windows)
            ? (data.interview_spine as { windows: unknown[] }).windows.length
            : "—"}{" "}
          windows · use pipeline gate to query moments
        </p>
      ) : null}
      <CoherenceRisksPanel />
      <div className="story-actions">
        <button type="button" className="btn" disabled={saving} onClick={() => void save(false)}>
          Save story
        </button>
        <button type="button" className="btn primary" disabled={saving} onClick={() => void save(true)}>
          {saving ? (
            <>
              <span className="spinner-inline" aria-hidden /> Locking…
            </>
          ) : (
            "Lock story for podcast edit"
          )}
        </button>
        <button type="button" className="btn ghost" onClick={() => setPipelineSubTab("timeline")}>
          Edit timeline
        </button>
      </div>
    </>
  );

  return (
    <GatePanelShell
      complete={storyComplete}
      title="Story Board complete — profile verified, investigations resolved"
      className="story-board panel"
    >
      {body}
    </GatePanelShell>
  );
}
