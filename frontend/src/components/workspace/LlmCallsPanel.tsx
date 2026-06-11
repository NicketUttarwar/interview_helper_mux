import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type {
  LlmCallRecord,
  LlmCallSummary,
  LlmCallsIndex,
  LlmCallVolleyTurn,
  LlmRoutingAttempt,
} from "../../types";

type EditState = {
  system_prompt: string;
  turns: LlmCallVolleyTurn[];
  raw_response: string;
};

function importanceClass(imp?: string): string {
  if (imp === "high") return "importance-high";
  if (imp === "medium") return "importance-medium";
  return "importance-low";
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    /* ignore */
  }
}

function CollapsibleSection({
  title,
  badge,
  defaultOpen = false,
  children,
  onCopy,
}: {
  title: string;
  badge?: string;
  defaultOpen?: boolean;
  children: ReactNode;
  onCopy?: () => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`llm-collapsible${open ? " open" : ""}`}>
      <div className="llm-collapsible-head">
        <button
          type="button"
          className="llm-collapsible-toggle"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
          <span className="llm-chevron">{open ? "▼" : "▶"}</span>
          <span className="llm-collapsible-title">{title}</span>
          {badge ? <span className="llm-badge">{badge}</span> : null}
        </button>
        {onCopy ? (
          <button type="button" className="btn ghost sm" onClick={onCopy}>
            Copy
          </button>
        ) : null}
      </div>
      {open ? <div className="llm-collapsible-body">{children}</div> : null}
    </div>
  );
}

function CallEditor({
  record,
  edit,
  onEdit,
  onSave,
  saving,
}: {
  record: LlmCallRecord;
  edit: EditState;
  onEdit: (next: EditState) => void;
  onSave: () => void;
  saving: boolean;
}) {
  const env = record.response?.parsed_envelope;
  return (
    <div className="llm-call-editor">
      <p className="llm-call-meta">
        <code>{record.label}</code>
        {" · "}
        {record.model_id} ({record.model_tier}) · {record.context_chars?.toLocaleString()} chars
        {record.truncation_flags?.length ? (
          <> · truncated: {record.truncation_flags.join(", ")}</>
        ) : null}
      </p>

      <CollapsibleSection
        title="System prompt"
        badge={edit.system_prompt ? `${edit.system_prompt.length} chars` : "empty"}
        defaultOpen={false}
        onCopy={() => void copyText(edit.system_prompt)}
      >
        <textarea
          className="artifact-editor"
          rows={6}
          value={edit.system_prompt}
          onChange={(e) => onEdit({ ...edit, system_prompt: e.target.value })}
          spellCheck={false}
        />
      </CollapsibleSection>

      {edit.turns.map((turn, idx) => (
        <CollapsibleSection
          key={`${turn.role}-${idx}`}
          title={`Volley turn ${idx + 1} — ${turn.role}`}
          badge={`${turn.content.length} chars`}
          defaultOpen={idx < 2}
          onCopy={() => void copyText(turn.content)}
        >
          <textarea
            className="artifact-editor"
            rows={8}
            value={turn.content}
            onChange={(e) => {
              const turns = [...edit.turns];
              turns[idx] = { ...turn, content: e.target.value };
              onEdit({ ...edit, turns });
            }}
            spellCheck={false}
          />
        </CollapsibleSection>
      ))}

      <div className="llm-turn-actions">
        <button
          type="button"
          className="btn ghost sm"
          onClick={() =>
            onEdit({
              ...edit,
              turns: [...edit.turns, { role: "user", content: "" }],
            })
          }
        >
          + User turn
        </button>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() =>
            onEdit({
              ...edit,
              turns: [...edit.turns, { role: "assistant", content: "" }],
            })
          }
        >
          + Assistant turn
        </button>
        {edit.turns.length > 0 ? (
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => onEdit({ ...edit, turns: edit.turns.slice(0, -1) })}
          >
            Remove last turn
          </button>
        ) : null}
      </div>

      <CollapsibleSection
        title="Assistant response (raw)"
        badge={edit.raw_response ? `${edit.raw_response.length} chars` : "empty"}
        defaultOpen={true}
        onCopy={() => void copyText(edit.raw_response)}
      >
        <textarea
          className="artifact-editor"
          rows={10}
          value={edit.raw_response}
          onChange={(e) => onEdit({ ...edit, raw_response: e.target.value })}
          spellCheck={false}
        />
      </CollapsibleSection>

      {env ? (
        <CollapsibleSection title="Parsed envelope (read-only)" defaultOpen={false}>
          <pre className="llm-envelope-preview">
            {JSON.stringify(
              {
                status: env.status,
                confidence: env.confidence,
                reasoning_summary: env.reasoning_summary,
                artifact_keys: env.artifacts
                  ? Object.keys(env.artifacts as object)
                  : [],
              },
              null,
              2,
            )}
          </pre>
        </CollapsibleSection>
      ) : null}

      <div className="llm-save-row">
        <button type="button" className="btn primary sm" disabled={saving} onClick={onSave}>
          {saving ? "Saving…" : "Save call record"}
        </button>
        <span className="muted sm">
          Updates volley + request.messages on disk (for copy-paste and future reruns).
        </span>
      </div>
    </div>
  );
}

export function LlmCallsPanel() {
  const { run, showToast, appendClientLog } = useApp();
  const [index, setIndex] = useState<LlmCallsIndex | null>(null);
  const [loading, setLoading] = useState(false);
  const [stageFilter, setStageFilter] = useState("");
  const [importanceFilter, setImportanceFilter] = useState("");
  const [search, setSearch] = useState("");
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set());
  const [expandedAttempts, setExpandedAttempts] = useState<Set<string>>(new Set());
  const [expandedCalls, setExpandedCalls] = useState<Set<string>>(new Set());
  const [records, setRecords] = useState<Record<string, LlmCallRecord>>({});
  const [edits, setEdits] = useState<Record<string, EditState>>({});
  const [savingPath, setSavingPath] = useState<string | null>(null);
  const [routingAttempts, setRoutingAttempts] = useState<LlmRoutingAttempt[]>([]);

  const loadIndex = useCallback(async () => {
    if (!run) return;
    setLoading(true);
    try {
      const [data, routing] = await Promise.all([
        api<LlmCallsIndex>(`/api/runs/${run.run_id}/llm-calls`),
        api<{ attempts: LlmRoutingAttempt[] }>(`/api/runs/${run.run_id}/llm-routing`).catch(
          () => ({ attempts: [] as LlmRoutingAttempt[] }),
        ),
      ]);
      setRoutingAttempts(routing.attempts || []);
      setIndex(data);
      if (data.stages.length === 1) {
        setExpandedStages(new Set(data.stages));
      }
    } catch (e) {
      setIndex(null);
      const msg = e instanceof Error ? e.message : "Failed to load LLM calls";
      showToast(msg);
      appendClientLog(msg, "warning");
    } finally {
      setLoading(false);
    }
  }, [run, showToast, appendClientLog]);

  useEffect(() => {
    void loadIndex();
  }, [loadIndex]);

  const filteredTree = useMemo(() => {
    if (!index) return { stages: [] as string[], tree: {} as LlmCallsIndex["tree"] };
    const stages = index.stages.filter((s) => !stageFilter || s === stageFilter);
    const tree: LlmCallsIndex["tree"] = {};
    for (const stage of stages) {
      const attempts = index.tree[stage];
      if (!attempts) continue;
      const filteredAttempts: Record<string, LlmCallSummary[]> = {};
      for (const [attemptKey, calls] of Object.entries(attempts)) {
        const filtered = calls.filter((c) => {
          if (importanceFilter && c.importance !== importanceFilter) return false;
          if (search) {
            const hay = `${c.label || ""} ${c.task_kind || ""} ${c.path}`.toLowerCase();
            if (!hay.includes(search.toLowerCase())) return false;
          }
          return true;
        });
        if (filtered.length) filteredAttempts[attemptKey] = filtered;
      }
      if (Object.keys(filteredAttempts).length) tree[stage] = filteredAttempts;
    }
    return { stages: Object.keys(tree), tree };
  }, [index, stageFilter, importanceFilter, search]);

  const loadRecord = useCallback(
    async (path: string) => {
      if (!run || records[path]) return;
      const data = await api<LlmCallRecord>(
        `/api/runs/${run.run_id}/llm-calls/record?path=${encodeURIComponent(path)}`,
      );
      setRecords((prev) => ({ ...prev, [path]: data }));
      const turns = (data.volley?.turns || []).map((t) => ({
        role: (t.role === "assistant" ? "assistant" : "user") as "user" | "assistant",
        content: t.content || "",
      }));
      setEdits((prev) => ({
        ...prev,
        [path]: {
          system_prompt: data.volley?.system_prompt || "",
          turns,
          raw_response: data.response?.raw_content || "",
        },
      }));
    },
    [run, records],
  );

  const toggleCall = async (path: string) => {
    const next = new Set(expandedCalls);
    if (next.has(path)) {
      next.delete(path);
    } else {
      next.add(path);
      try {
        await loadRecord(path);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to load call";
        showToast(msg);
        appendClientLog(msg, "warning");
        return;
      }
    }
    setExpandedCalls(next);
  };

  const saveCall = async (path: string) => {
    if (!run) return;
    const edit = edits[path];
    if (!edit) return;
    setSavingPath(path);
    try {
      const res = await api<{ ok: boolean; record: LlmCallRecord }>(
        `/api/runs/${run.run_id}/llm-calls/record`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            path,
            volley: {
              system_prompt: edit.system_prompt,
              turns: edit.turns,
            },
            raw_response: edit.raw_response,
          }),
        },
      );
      setRecords((prev) => ({ ...prev, [path]: res.record }));
      showToast("LLM call saved");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Save failed";
      showToast(msg);
      appendClientLog(msg, "warning");
    } finally {
      setSavingPath(null);
    }
  };

  const expandAll = () => {
    if (!index) return;
    setExpandedStages(new Set(filteredTree.stages));
    const attempts = new Set<string>();
    const calls = new Set<string>();
    for (const stage of filteredTree.stages) {
      for (const [attemptKey, list] of Object.entries(filteredTree.tree[stage] || {})) {
        attempts.add(`${stage}:${attemptKey}`);
        for (const c of list) calls.add(c.path);
      }
    }
    setExpandedAttempts(attempts);
    setExpandedCalls(calls);
    void Promise.all([...calls].map((p) => loadRecord(p))).catch(() => {
      const msg = "Some calls failed to load";
      showToast(msg);
      appendClientLog(msg, "warning");
    });
  };

  const collapseAll = () => {
    setExpandedStages(new Set());
    setExpandedAttempts(new Set());
    setExpandedCalls(new Set());
  };

  if (!run) return null;

  return (
    <div className="panel llm-calls-panel">
      <header className="llm-calls-header">
        <div>
          <h2>OpenAI API calls</h2>
          <p className="lead sm">
            Every Chat Completions request for this execution — system prompt, user/assistant
            volley, and model response. Edit and save to refine context for future runs.
          </p>
        </div>
        <div className="llm-calls-toolbar">
          <button type="button" className="btn ghost sm" onClick={() => void loadIndex()}>
            Refresh
          </button>
          <button type="button" className="btn ghost sm" onClick={expandAll}>
            Expand all
          </button>
          <button type="button" className="btn ghost sm" onClick={collapseAll}>
            Collapse all
          </button>
        </div>
      </header>

      <div className="llm-filters">
        <label>
          Stage
          <select
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className="select"
          >
            <option value="">All stages</option>
            {(index?.stages || []).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Importance
          <select
            value={importanceFilter}
            onChange={(e) => setImportanceFilter(e.target.value)}
            className="select"
          >
            <option value="">All</option>
            <option value="high">High (primary, arbiter, collate)</option>
            <option value="medium">Medium (shard, specialist)</option>
            <option value="low">Low</option>
          </select>
        </label>
        <label className="llm-search-label">
          Search label
          <input
            type="search"
            className="select"
            placeholder="e.g. arbiter, missing_framing"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <span className="llm-count muted">
          {loading ? "Loading…" : `${index?.call_count ?? 0} calls recorded`}
        </span>
      </div>

      {routingAttempts.length > 0 ? (
        <div className="llm-routing-panel llm-calls-routing-summary">
          <h3 className="stage-outputs-title">Arbiter routing</h3>
          <ul className="llm-routing-list">
            {routingAttempts.slice(0, 12).map((r, i) => (
              <li key={`${r.stage}-${r.attempt ?? i}`}>
                <span className="llm-routing-task">
                  {r.stage} · {r.task_kind || "primary"}
                  {r.attempt ? ` #${r.attempt}` : ""}
                </span>
                <span className={`llm-routing-verdict verdict-${r.verdict || "unknown"}`}>
                  {r.verdict || "—"}
                </span>
                {r.primary_attempt_count != null && r.budget_remaining_primary != null ? (
                  <span className="routing-budget-badge">
                    {r.primary_attempt_count}/{r.primary_attempt_count + r.budget_remaining_primary}
                  </span>
                ) : null}
                {r.deterministic_lint_errors?.length ? (
                  <span className="lint-error-chip" title={r.deterministic_lint_errors.join("; ")}>
                    lint fail
                  </span>
                ) : null}
                {(r.stuck_count ?? 0) > 0 ? (
                  <span className="routing-stuck-badge">stuck ×{r.stuck_count}</span>
                ) : null}
                {r.arbiter_reason ? (
                  <span className="hint sm">{r.arbiter_reason}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!loading && index && index.call_count === 0 ? (
        <p className="empty-state">
          No LLM call records yet. Run analysis or flow stages with{" "}
          <code>analysis.llm_call_records.enabled</code> (default on). Records appear under{" "}
          <code>understanding/llm_calls/</code>.
        </p>
      ) : null}

      <div className="llm-tree">
        {filteredTree.stages.map((stage) => {
          const stageOpen = expandedStages.has(stage);
          const attempts = filteredTree.tree[stage] || {};
          return (
            <div key={stage} className="llm-tree-stage">
              <button
                type="button"
                className="llm-tree-stage-head"
                onClick={() => {
                  const next = new Set(expandedStages);
                  if (stageOpen) next.delete(stage);
                  else next.add(stage);
                  setExpandedStages(next);
                }}
              >
                <span className="llm-chevron">{stageOpen ? "▼" : "▶"}</span>
                <strong>{stage}</strong>
                <span className="muted">
                  {Object.values(attempts).reduce((n, arr) => n + arr.length, 0)} calls
                </span>
              </button>
              {stageOpen
                ? Object.entries(attempts)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([attemptKey, calls]) => {
                      const attemptId = `${stage}:${attemptKey}`;
                      const attemptOpen = expandedAttempts.has(attemptId);
                      return (
                        <div key={attemptId} className="llm-tree-attempt">
                          <button
                            type="button"
                            className="llm-tree-attempt-head"
                            onClick={() => {
                              const next = new Set(expandedAttempts);
                              if (attemptOpen) next.delete(attemptId);
                              else next.add(attemptId);
                              setExpandedAttempts(next);
                            }}
                          >
                            <span className="llm-chevron">{attemptOpen ? "▼" : "▶"}</span>
                            {attemptKey.replace("_", " ")}
                            <span className="muted">({calls.length})</span>
                          </button>
                          {attemptOpen
                            ? calls.map((c) => {
                                const open = expandedCalls.has(c.path);
                                const record = records[c.path];
                                const edit = edits[c.path];
                                return (
                                  <div
                                    key={c.path}
                                    className={`llm-tree-call ${importanceClass(c.importance)}`}
                                  >
                                    <button
                                      type="button"
                                      className="llm-tree-call-head"
                                      onClick={() => void toggleCall(c.path)}
                                    >
                                      <span className="llm-chevron">{open ? "▼" : "▶"}</span>
                                      <span className="llm-call-seq">
                                        {String(c.sequence).padStart(2, "0")}
                                      </span>
                                      <span className="llm-call-task">{c.task_kind}</span>
                                      <span
                                        className={`llm-importance ${importanceClass(c.importance)}`}
                                      >
                                        {c.importance}
                                      </span>
                                      <code className="llm-call-label">{c.label}</code>
                                    </button>
                                    {open && record && edit ? (
                                      <CallEditor
                                        record={record}
                                        edit={edit}
                                        onEdit={(next) =>
                                          setEdits((prev) => ({ ...prev, [c.path]: next }))
                                        }
                                        onSave={() => void saveCall(c.path)}
                                        saving={savingPath === c.path}
                                      />
                                    ) : null}
                                    {open && !record ? (
                                      <p className="muted sm">Loading call…</p>
                                    ) : null}
                                  </div>
                                );
                              })
                            : null}
                        </div>
                      );
                    })
                : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
