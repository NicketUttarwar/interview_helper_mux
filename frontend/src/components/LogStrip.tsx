import { useApp } from "../context/AppContext";
import { escapeHtml, formatTs } from "../utils";
import { stageTitleById } from "../utils/logDisplay";

export function LogStrip() {
  const { logEntries, run, setActiveTab } = useApp();
  const tail = logEntries.slice(-3);
  const actionCount = logEntries.filter((e) =>
    ["action", "warning", "error"].includes(e.level || ""),
  ).length;

  return (
    <footer
      className="log-strip"
      role="log"
      aria-live="polite"
      onClick={() => setActiveTab("logs")}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") setActiveTab("logs");
      }}
      tabIndex={0}
    >
      <div className="log-strip-head">
        <span className="log-strip-title">Operator log</span>
        {actionCount > 0 ? (
          <span className="log-strip-badge">{actionCount} alerts</span>
        ) : null}
        <span className="log-strip-hint muted">Click for full log</span>
      </div>
      <div className="log-strip-body">
        {!tail.length ? (
          <span className="muted">Log entries appear here as the pipeline runs.</span>
        ) : (
          tail.map((e, i) => (
            <div key={`${e.ts}-${i}`} className={`log-entry level-${e.level || "info"}`}>
              <span className={`log-level-dot level-${e.level || "info"}`} aria-hidden />
              <span className="log-ts">{formatTs(e.ts)}</span>
              {e.stage ? (
                <span className="log-stage-mini">
                  {stageTitleById(run?.stages, e.stage) ?? e.stage}
                </span>
              ) : null}
              <span className="log-msg">{escapeHtml(e.message)}</span>
            </div>
          ))
        )}
      </div>
    </footer>
  );
}
