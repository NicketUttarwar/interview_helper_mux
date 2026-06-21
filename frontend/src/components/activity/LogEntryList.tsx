import { useEffect, useState } from "react";
import type { LogEntry } from "../../types";
import { escapeHtml, formatTs, parseLogDetail } from "../../utils";
import {
  formatLogDetailBlock,
  logJourneyKind,
  stageTitleById,
} from "../../utils/logDisplay";
import type { RunData } from "../../types";

interface Props {
  entries: LogEntry[];
  run: RunData | null;
  emptyMessage?: string;
  onStageClick?: (stageId: string) => void;
  compact?: boolean;
}

function errorIndices(entries: LogEntry[]): Set<number> {
  const set = new Set<number>();
  entries.forEach((e, i) => {
    if (e.level === "error") set.add(i);
  });
  return set;
}

function copyEntryText(entry: LogEntry): string {
  const detailBlock = formatLogDetailBlock(entry.detail);
  const lines = [entry.message];
  if (detailBlock.text.trim()) lines.push(detailBlock.text);
  return lines.join("\n\n");
}

export function LogEntryList({
  entries,
  run,
  emptyMessage = "No log entries.",
  onStageClick,
  compact = false,
}: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(() => errorIndices(entries));

  useEffect(() => {
    setExpanded((prev) => {
      const next = new Set(prev);
      errorIndices(entries).forEach((i) => next.add(i));
      return next;
    });
  }, [entries]);

  if (!entries.length) {
    return <p className="log-empty muted">{emptyMessage}</p>;
  }

  return (
    <>
      {entries.map((e, i) => {
        const journeyKind = logJourneyKind(e.detail);
        const detailBlock = formatLogDetailBlock(e.detail);
        const parsed = parseLogDetail(e.detail as string | Record<string, unknown> | null | undefined);
        const stream = parsed?.stream;
        const isStream = stream === "stdout" || stream === "stderr";
        const isError = e.level === "error";
        return (
          <div
            key={`${e.ts}-${i}-${e.message.slice(0, 20)}`}
            className={`log-entry level-${e.level || "info"}${compact ? " log-entry-compact" : ""}${isStream ? " log-entry-stream" : ""}`}
          >
            <div className="log-entry-main">
              <span className="log-ts">{formatTs(e.ts)}</span>
              {!compact ? (
                <span className={`log-level-badge level-${e.level || "info"}`}>
                  {e.level || "info"}
                </span>
              ) : (
                <span className={`log-level-dot level-${e.level || "info"}`} aria-hidden />
              )}
              {isStream ? (
                <span className="log-stream-badge">{String(stream)}</span>
              ) : null}
              {e.stage ? (
                onStageClick ? (
                  <button
                    type="button"
                    className="log-stage log-stage-btn"
                    title={e.stage}
                    onClick={() => onStageClick(e.stage!)}
                  >
                    {stageTitleById(run?.stages, e.stage) ?? e.stage}
                  </button>
                ) : (
                  <span className="log-stage" title={e.stage}>
                    {stageTitleById(run?.stages, e.stage) ?? e.stage}
                  </span>
                )
              ) : null}
              {journeyKind ? (
                <span className="log-journey-badge">{journeyKind}</span>
              ) : null}
              <span className={`log-msg${isStream ? " log-msg-mono" : ""}`}>
                {escapeHtml(e.message)}
              </span>
              {isError ? (
                <button
                  type="button"
                  className="btn ghost sm log-copy-btn"
                  title="Copy error"
                  onClick={() => {
                    void navigator.clipboard.writeText(copyEntryText(e));
                  }}
                >
                  Copy
                </button>
              ) : null}
            </div>
            {e.detail && !compact && !isStream ? (
              <>
                <button
                  type="button"
                  className="btn ghost sm log-detail-toggle"
                  onClick={() =>
                    setExpanded((prev) => {
                      const next = new Set(prev);
                      if (next.has(i)) next.delete(i);
                      else next.add(i);
                      return next;
                    })
                  }
                >
                  {expanded.has(i) ? "Hide detail" : "Show detail"}
                </button>
                {expanded.has(i) ? (
                  <pre
                    className={`log-detail${detailBlock.isJson ? " log-detail-json" : ""}`}
                  >
                    {escapeHtml(detailBlock.text)}
                  </pre>
                ) : null}
              </>
            ) : null}
          </div>
        );
      })}
    </>
  );
}
