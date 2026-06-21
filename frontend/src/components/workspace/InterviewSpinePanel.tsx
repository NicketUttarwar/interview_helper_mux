import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { SPINE_PATH } from "../../utils";
import { formatApiError } from "../../utils/safeApi";
import { GatePanelShell } from "../pipeline/GatePanelShell";

interface SpineSummary {
  window_total?: number;
  retrieval?: { enabled?: boolean; window_count?: number };
  boundary_events?: Array<Record<string, unknown>>;
  speaker_stats?: Array<Record<string, unknown>>;
}

interface QueryHit {
  window_id?: string;
  start_ms?: number;
  end_ms?: number;
  text_span?: string;
  score?: number;
}

export function InterviewSpinePanel() {
  const { run, selectedStage, refreshRun, showToast, appendClientLog, confirm } = useApp();
  const [summary, setSummary] = useState<SpineSummary | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<QueryHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const spineStage =
    selectedStage?.id === "interview_spine_build"
      ? selectedStage
      : run?.stages.find((s) => s.id === "interview_spine_build");
  const spineComplete = spineStage?.status === "done";

  const load = useCallback(async () => {
    if (!run) return;
    setLoadError(null);
    try {
      const data = await api<SpineSummary>(
        `/api/runs/${run.run_id}/interview-spine?offset=0&limit=1`,
      );
      setSummary(data);
    } catch (e) {
      setSummary(null);
      const msg = formatApiError(e, "Interview spine");
      setLoadError(msg);
      appendClientLog(msg, "error");
    }
  }, [run, appendClientLog]);

  useEffect(() => {
    void load();
  }, [load]);

  const recompute = async () => {
    if (!run) return;
    if (!(await confirm("Recompute interview spine from current ingest/transcript/SAP?"))) return;
    setLoading(true);
    try {
      await api(`/api/runs/${run.run_id}/recompute-interview-spine`, { method: "POST" });
      showToast("Interview spine recomputed.");
      await refreshRun();
      await load();
    } catch (e) {
      const msg = formatApiError(e, "Recompute spine");
      showToast(msg, "error");
      appendClientLog(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  const runQuery = async () => {
    if (!run || !query.trim()) return;
    setLoading(true);
    try {
      const res = await api<{ hits?: QueryHit[] }>(
        `/api/runs/${run.run_id}/interview-spine/query`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: query.trim(), top_k: 5 }),
        },
      );
      setHits(res.hits || []);
    } catch (e) {
      const msg = formatApiError(e, "Spine query");
      showToast(msg, "error");
      appendClientLog(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  if (loadError && !summary) {
    return (
      <div className="quality-offer-card">
        <h4>Interview spine</h4>
        <p className="error-text" role="alert">
          {loadError}
        </p>
        <button type="button" className="btn ghost sm" onClick={() => void load()}>
          Retry
        </button>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="quality-offer-card">
        <h4>Interview spine</h4>
        <p className="hint">Run <strong>Interview comprehension spine</strong> after source acoustic profile.</p>
      </div>
    );
  }

  const events = summary.boundary_events || [];
  const retrievalOn = Boolean(summary.retrieval?.enabled);

  const body = (
    <>
      <h4>Interview spine</h4>
      <p className="muted sm">
        {summary.window_total ?? 0} windows · {events.length} boundary events · retrieval{" "}
        {retrievalOn ? "on" : "off"}
      </p>
      {events.length > 0 ? (
        <ul className="spine-event-list">
          {events.slice(0, 6).map((ev, idx) => (
            <li key={`${String(ev.time_ms)}-${idx}`}>
              {Math.round(Number(ev.time_ms || 0) / 1000)}s — {String(ev.type || "event")} (
              {String(ev.confidence ?? "—")})
            </li>
          ))}
        </ul>
      ) : null}
      <label className="field">
        Retrieval query
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. pricing objection"
        />
      </label>
      <div className="flow-choice">
        <button type="button" className="btn sm" disabled={loading} onClick={() => void runQuery()}>
          Search spine
        </button>
        <button type="button" className="btn sm primary" disabled={loading} onClick={() => void recompute()}>
          Recompute spine
        </button>
      </div>
      {hits.length > 0 ? (
        <ul className="spine-hit-list">
          {hits.map((hit) => (
            <li key={String(hit.window_id)}>
              <strong>{hit.window_id}</strong> ({Math.round(Number(hit.start_ms || 0) / 1000)}s) —{" "}
              {hit.text_span} <span className="muted">score {hit.score}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="muted sm">Artifact: {SPINE_PATH}</p>
    </>
  );

  return (
    <GatePanelShell
      complete={spineComplete}
      title="Interview spine complete"
      className="quality-offer-card interview-spine-card"
    >
      {body}
    </GatePanelShell>
  );
}
