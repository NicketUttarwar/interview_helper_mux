import { useState } from "react";
import type { LogEntry } from "../../types";
import { escapeHtml, formatTs } from "../../utils";
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

export function LogEntryList({
  entries,
  run,
  emptyMessage = "No log entries.",
  onStageClick,
  compact = false,
}: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());

  if (!entries.length) {
    return <p className="log-empty muted">{emptyMessage}</p>;
  }

  return (
    <>
      {entries.map((e, i) => {
        const journeyKind = logJourneyKind(e.detail);
        const detailBlock = formatLogDetailBlock(e.detail);
        return (
          <div
            key={`${e.ts}-${i}-${e.message.slice(0, 20)}`}
            className={`log-entry level-${e.level || "info"}${compact ? " log-entry-compact" : ""}`}
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
              <span className="log-msg">{escapeHtml(e.message)}</span>
            </div>
            {e.detail && !compact ? (
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
