import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useApp } from "../../context/AppContext";
import { escapeHtml, formatTs } from "../../utils";
import {
  formatLogDetailBlock,
  logJourneyKind,
  stageTitleById,
} from "../../utils/logDisplay";
import { parseLogDetail } from "../../utils";
import { buildStageProgress } from "../../utils/stageSubsteps";
import type { JourneyLogKind, LogEntry, LogLevel } from "../../types";

const LEVELS: LogLevel[] = ["info", "success", "warning", "error", "action"];

const JOURNEY_KINDS: JourneyLogKind[] = [
  "gate",
  "quality",
  "preview",
  "sfx",
  "qc",
  "milestone",
  "execute",
];

function isStreamLog(detail: LogEntry["detail"]): boolean {
  const parsed = parseLogDetail(detail as string | Record<string, unknown> | null | undefined);
  const stream = parsed?.stream;
  return stream === "stdout" || stream === "stderr";
}

export function LogsTab() {
  const {
    logEntries,
    runId,
    run,
    config,
    logFilterPreset,
    setLogFilterPreset,
    activateSubstep,
    apiGrants,
    jobRunning,
  } = useApp();
  const journeyFilterDefault = config?.journey_ui?.journey_log_filter === true;
  const [journeyFilter, setJourneyFilter] = useState(journeyFilterDefault);
  const [levelFilter, setLevelFilter] = useState<string>("all");
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [tailSize, setTailSize] = useState<number | "all">(200);
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);

  const onStageClick = useCallback(
    (stageId: string) => {
      if (!run) return;
      const stage = run.stages.find((s) => s.id === stageId);
      if (!stage) return;
      const progress = buildStageProgress(stage, run, { jobRunning, apiGrants });
      const target =
        progress.substeps.find((s) => s.status === "todo" || s.status === "running") ||
        progress.substeps[0];
      if (target) {
        activateSubstep(target, { openModal: target.kind === "gate" || target.kind === "checkpoint" });
      }
    },
    [run, jobRunning, apiGrants, activateSubstep],
  );

  useEffect(() => {
    if (jobRunning) setJourneyFilter(false);
  }, [jobRunning]);

  useEffect(() => {
    if (!logFilterPreset) return;
    if (logFilterPreset.level) setLevelFilter(logFilterPreset.level);
    if (logFilterPreset.stage) setStageFilter(logFilterPreset.stage);
    const scrollToError = logFilterPreset.scrollToError;
    setLogFilterPreset(null);
    if (scrollToError) {
      requestAnimationFrame(() => {
        scrollRef.current
          ?.querySelector(".log-entry.level-error")
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }
  }, [logFilterPreset, setLogFilterPreset]);

  const stageFilterOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const e of logEntries) {
      if (e.stage) ids.add(e.stage);
    }
    for (const s of run?.stages || []) {
      ids.add(s.id);
    }
    return [...ids]
      .sort()
      .map((id) => ({ id, title: stageTitleById(run?.stages, id) ?? id }));
  }, [logEntries, run?.stages]);

  const filtered = useMemo(() => {
    return logEntries.filter((e) => {
      if (journeyFilter) {
        const kind = logJourneyKind(e.detail);
        const isGate = e.level === "action";
        const isStream = isStreamLog(e.detail);
        if (!kind && !isGate && !isStream && e.level === "info") return false;
        if (kind && !JOURNEY_KINDS.includes(kind as JourneyLogKind) && !isGate && !isStream) {
          return false;
        }
      }
      if (levelFilter !== "all" && e.level !== levelFilter) return false;
      if (stageFilter !== "all" && e.stage !== stageFilter) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        const hay = `${e.message} ${e.stage || ""} ${typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail || "")}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [logEntries, levelFilter, stageFilter, search, journeyFilter]);

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
        <p className="hint logs-command-hint">
          {jobRunning
            ? "Job running — live command output streams below. Turn off Journey view to see every line."
            : "Current action is in the live status bar above. Use filters below to inspect history."}
        </p>
        <div className="logs-toolbar-actions">
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => {
              setLevelFilter("all");
              setStageFilter(
                run?.job?.current_stage || run?.job?.stage || "all",
              );
            }}
          >
            Jump to active stream
          </button>
        </div>
        <div className="logs-filters">
          <label className="logs-filter logs-filter-check">
            <input
              type="checkbox"
              checked={journeyFilter}
              onChange={(e) => setJourneyFilter(e.target.checked)}
            />
            Journey view
          </label>
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
              <option value="all">All stages</option>
              {stageFilterOptions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
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
            displayed.map((e, i) => {
              const journeyKind = logJourneyKind(e.detail);
              const detailBlock = formatLogDetailBlock(e.detail);
              return (
              <div key={`${e.ts}-${i}`} className={`log-entry level-${e.level || "info"}`}>
                <div className="log-entry-main">
                  <span className="log-ts">{formatTs(e.ts)}</span>
                  <span className={`log-level-badge level-${e.level || "info"}`}>
                    {e.level || "info"}
                  </span>
                  {e.stage ? (
                    <button
                      type="button"
                      className="log-stage log-stage-btn"
                      title={e.stage}
                      onClick={() => onStageClick(e.stage!)}
                    >
                      {stageTitleById(run?.stages, e.stage) ?? e.stage}
                    </button>
                  ) : null}
                  {journeyKind ? (
                    <span className="log-journey-badge">{journeyKind}</span>
                  ) : null}
                  <span className="log-msg">{escapeHtml(e.message)}</span>
                </div>
                {e.detail ? (
                  <>
                    <button
                      type="button"
                      className="btn ghost sm log-detail-toggle"
                      onClick={() => toggleExpand(i)}
                    >
                      {expanded.has(i) ? "Hide detail" : "Show detail"}
                    </button>
                    {expanded.has(i) ? (
                      <pre className={`log-detail${detailBlock.isJson ? " log-detail-json" : ""}`}>
                        {escapeHtml(detailBlock.text)}
                      </pre>
                    ) : null}
                  </>
                ) : null}
              </div>
            );
            })
          )}
        </div>
      </section>
    </main>
  );
}
