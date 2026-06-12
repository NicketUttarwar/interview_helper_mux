import { useApp } from "../../context/AppContext";
import { filterLiveStream, latestEntry } from "../../utils/logStreams";
import { escapeHtml, formatTs } from "../../utils";

export function ActivityTeaser() {
  const {
    activeTab,
    logEntries,
    run,
    jobRunning,
    setActiveTab,
    setActivityLogCollapsed,
  } = useApp();

  if (activeTab === "pipeline") return null;

  const live = filterLiveStream(logEntries, run, jobRunning);
  const last = latestEntry(live) || latestEntry(logEntries);

  return (
    <footer
      className="activity-teaser log-strip"
      data-testid="activity-teaser"
      role="log"
      aria-live="polite"
      tabIndex={0}
      onClick={() => {
        setActiveTab("pipeline");
        setActivityLogCollapsed(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          setActiveTab("pipeline");
          setActivityLogCollapsed(false);
        }
      }}
    >
      <div className="log-strip-head">
        <span className="log-strip-title">Latest activity</span>
        <span className="log-strip-hint muted">Open Pipeline activity →</span>
      </div>
      <div className="log-strip-body">
        {!last ? (
          <span className="muted">Activity appears here as the pipeline runs.</span>
        ) : (
          <div className={`log-entry level-${last.level || "info"}`}>
            <span className="log-ts">{formatTs(last.ts)}</span>
            <span className="log-msg">{escapeHtml(last.message)}</span>
          </div>
        )}
      </div>
    </footer>
  );
}
