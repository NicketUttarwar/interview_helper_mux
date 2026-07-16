import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { ContextIndexSummary, VolleyEntry } from "../../types";

import { formatApiError, isExpectedEmptyApiError } from "../../utils/safeApi";

const KINDS = [
  "stage_conclusion",
  "investigation",
  "profile_digest",
  "shard_summary",
  "specialist_finding",
  "artifact_digest",
  "local_framing",
] as const;

export function VolleyMemoryPanel() {
  const { runId, setPipelineSubTab, showToast, appendClientLog } = useApp();
  const [data, setData] = useState<ContextIndexSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterKind, setFilterKind] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState<string>("active");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api<ContextIndexSummary>(`/api/runs/${runId}/context-index`);
      setData(res);
    } catch (e) {
      const msg = formatApiError(e, "Volley memory");
      setError(msg);
      if (!isExpectedEmptyApiError(e)) {
        appendClientLog(msg, "error");
      }
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const entries = useMemo(() => {
    const list = data?.index?.volley_entries ?? [];
    return list.filter((e) => {
      if (filterKind && e.kind !== filterKind) return false;
      if (filterStatus && e.status !== filterStatus) return false;
      return true;
    });
  }, [data, filterKind, filterStatus]);

  const openEntry = (entry: VolleyEntry) => {
    setExpandedId(entry.entry_id);
    setEditContent(entry.content);
  };

  const saveEntry = async (entryId: string) => {
    if (!runId) return;
    setSaving(true);
    try {
      await api(`/api/runs/${runId}/context-index/entries/${encodeURIComponent(entryId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editContent }),
      });
      await load();
    } catch (e) {
      const msg = formatApiError(e, "Save volley entry");
      setError(msg);
      appendClientLog(msg, "error");
    } finally {
      setSaving(false);
    }
  };

  const invalidateEntry = async (entryId: string) => {
    if (!runId) return;
    try {
      await api(`/api/runs/${runId}/context-index/entries/${encodeURIComponent(entryId)}/invalidate`, {
        method: "POST",
      });
      await load();
    } catch (e) {
      const msg = formatApiError(e, "Invalidate volley entry");
      setError(msg);
      appendClientLog(msg, "error");
    }
  };

  const addEntry = async () => {
    if (!runId) return;
    try {
      await api(`/api/runs/${runId}/context-index/entries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "stage_conclusion",
          role: "assistant",
          content: "Operator note: ",
          source: { stage_key: "operator", task_kind: "manual" },
        }),
      });
      await load();
    } catch (e) {
      const msg = formatApiError(e, "Add volley entry");
      setError(msg);
      appendClientLog(msg, "error");
    }
  };

  const rebuild = async () => {
    if (!runId) return;
    setLoading(true);
    try {
      await api(`/api/runs/${runId}/context-index/rebuild`, { method: "POST" });
      await load();
    } catch (e) {
      const msg = formatApiError(e, "Rebuild volley memory");
      setError(msg);
      appendClientLog(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  const openLlmCall = (path: string) => {
    sessionStorage.setItem("volley_llm_call_path", path);
    setPipelineSubTab("llm_calls");
  };

  if (!runId) {
    return <p className="hint">Select a run to view volley memory.</p>;
  }

  return (
    <section className="panel volley-memory-panel">
      <header className="panel-head">
        <h2>Volley memory</h2>
        <p className="hint">
          Q&amp;A entries from accepted stages — used when{" "}
          <code>prefer_index_over_legacy_summaries</code> is enabled.
        </p>
        <div className="row gap-sm">
          <button type="button" className="btn ghost sm" onClick={() => void load()} disabled={loading}>
            {loading ? (
              <>
                <span className="spinner-inline" aria-hidden /> Refreshing…
              </>
            ) : (
              "Refresh"
            )}
          </button>
          <button type="button" className="btn ghost sm" onClick={() => void addEntry()}>
            Add entry
          </button>
          <button type="button" className="btn ghost sm" onClick={() => void rebuild()} disabled={loading}>
            {loading ? (
              <>
                <span className="spinner-inline" aria-hidden /> Rebuilding…
              </>
            ) : (
              "Rebuild from disk"
            )}
          </button>
        </div>
      </header>

      {data?.stats ? (
        <p className="hint">
          {data.stats.total} entries —{" "}
          {Object.entries(data.stats.by_kind)
            .map(([k, n]) => `${k}: ${n}`)
            .join(", ")}
        </p>
      ) : null}

      <div className="row gap-sm volley-filters">
        <label>
          Kind{" "}
          <select value={filterKind} onChange={(e) => setFilterKind(e.target.value)}>
            <option value="">All</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status{" "}
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="">All</option>
            <option value="active">active</option>
            <option value="superseded">superseded</option>
            <option value="invalidated">invalidated</option>
          </select>
        </label>
      </div>

      {error ? <p className="error-text">{error}</p> : null}
      {loading && !data ? <p className="hint">Loading…</p> : null}
      {!loading && data && entries.length === 0 ? (
        <p className="hint">No volley memory entries yet — they appear as analysis stages complete.</p>
      ) : null}

      <p className="hint sm volley-scroll-hint">Scroll horizontally on narrow screens to see all columns.</p>

      <table className="volley-table">
        <thead>
          <tr>
            <th aria-label="Expand" />
            <th>Kind</th>
            <th>Source</th>
            <th>Status</th>
            <th>Chars</th>
            <th>Preview</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <Fragment key={entry.entry_id}>
              <tr
                className={expandedId === entry.entry_id ? "expanded" : ""}
                onClick={() => openEntry(entry)}
              >
                <td className="volley-expand-cell" aria-hidden>
                  {expandedId === entry.entry_id ? "▼" : "▶"}
                </td>
                <td>{entry.kind}</td>
                <td>{entry.source?.stage_key ?? "—"}</td>
                <td>{entry.status}</td>
                <td>{entry.char_count ?? entry.content.length}</td>
                <td className="volley-preview">{entry.content.slice(0, 80)}…</td>
              </tr>
              {expandedId === entry.entry_id ? (
                <tr key={`${entry.entry_id}-edit`}>
                  <td colSpan={6}>
                    <textarea
                      className="volley-editor"
                      rows={6}
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                    />
                    <div className="row gap-sm">
                      <button
                        type="button"
                        className="btn primary sm"
                        disabled={saving}
                        onClick={() => void saveEntry(entry.entry_id)}
                      >
                        {saving ? (
                          <>
                            <span className="spinner-inline" aria-hidden /> Saving…
                          </>
                        ) : (
                          "Save"
                        )}
                      </button>
                      <button
                        type="button"
                        className="btn ghost sm"
                        onClick={() => void invalidateEntry(entry.entry_id)}
                      >
                        Invalidate
                      </button>
                      {entry.source?.llm_call_path ? (
                        <button
                          type="button"
                          className="btn ghost sm"
                          onClick={() => openLlmCall(entry.source!.llm_call_path!)}
                        >
                          Open LLM call
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
      {!loading && entries.length === 0 ? (
        <p className="hint">No volley entries match filters. Run analysis stages or use Rebuild.</p>
      ) : null}
    </section>
  );
}
