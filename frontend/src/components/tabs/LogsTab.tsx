import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";
import type { LogLevel } from "../../types";

const LEVELS: LogLevel[] = ["info", "success", "warning", "error", "action"];

export function LogsTab() {
  const { logEntries, runId, run } = useApp();
  const [levelFilter, setLevelFilter] = useState<string>("all");
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [tailSize, setTailSize] = useState<number | "all">(200);
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);

  const stages = useMemo(() => {
    const set = new Set<string>();
    for (const e of logEntries) {
      if (e.stage) set.add(e.stage);
    }
    return [...set].sort();
  }, [logEntries]);

  const filtered = useMemo(() => {
    return logEntries.filter((e) => {
      if (levelFilter !== "all" && e.level !== levelFilter) return false;
      if (stageFilter !== "all" && e.stage !== stageFilter) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        const hay = `${e.message} ${e.stage || ""} ${typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail || "")}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [logEntries, levelFilter, stageFilter, search]);

  const displayed = useMemo(() => {
    if (tailSize === "all") return filtered;
    return filtered.slice(-tailSize);
  }, [filtered, tailSize]);

  useEffect(() => {
    if (!autoScroll || userScrolledRef.current || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [displayed, autoScroll]);

  const toggleExpand = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <main className="view tab-view logs-tab">
      <section className="panel logs-panel">
        <div className="panel-head logs-toolbar">
          <h3>Operator log</h3>
          <span className="hint">
            {runId ? run?.run_id : "No run"} · persisted to <code>gui_log.jsonl</code>
          </span>
        </div>
        <div className="logs-filters">
          <label className="logs-filter">
            Level
            <select
              className="select sm"
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value)}
            >
              <option value="all">All</option>
              {LEVELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className="logs-filter">
            Stage
            <select
              className="select sm"
              value={stageFilter}
              onChange={(e) => setStageFilter(e.target.value)}
            >
              <option value="all">All</option>
              {stages.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="logs-filter logs-filter-grow">
            Search
            <input
              type="search"
              className="input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter messages…"
            />
          </label>
          <label className="logs-filter">
            Tail
            <select
              className="select sm"
              value={String(tailSize)}
              onChange={(e) => {
                const v = e.target.value;
                setTailSize(v === "all" ? "all" : Number(v));
              }}
            >
              <option value="200">200</option>
              <option value="500">500</option>
              <option value="all">All fetched</option>
            </select>
          </label>
          <label className="logs-filter logs-filter-check">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => {
                setAutoScroll(e.target.checked);
                userScrolledRef.current = !e.target.checked;
              }}
            />
            Auto-scroll
          </label>
        </div>
        <div
          ref={scrollRef}
          className="prompt-log logs-full"
          role="log"
          aria-live="polite"
          onScroll={() => {
            if (!scrollRef.current) return;
            const el = scrollRef.current;
            const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
            userScrolledRef.current = !atBottom;
          }}
        >
          {!displayed.length ? (
            <p className="log-empty">No log entries match your filters.</p>
          ) : (
            displayed.map((e, i) => (
              <div key={`${e.ts}-${i}`} className={`log-entry level-${e.level || "info"}`}>
                <span className="log-ts">{formatTs(e.ts)}</span>
                {e.stage ? <span className="log-stage">[{e.stage}]</span> : null}
                <span className="log-msg">{escapeHtml(e.message)}</span>
                {e.detail ? (
                  <>
                    <button
                      type="button"
                      className="btn ghost sm log-detail-toggle"
                      onClick={() => toggleExpand(i)}
                    >
                      {expanded.has(i) ? "Hide detail" : "Detail"}
                    </button>
                    {expanded.has(i) ? (
                      <div className="log-detail">
                        {escapeHtml(
                          typeof e.detail === "string"
                            ? e.detail
                            : JSON.stringify(e.detail, null, 2),
                        )}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>
            ))
          )}
        </div>
      </section>
    </main>
  );
}
