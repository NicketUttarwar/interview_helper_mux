import { useApp } from "../../context/AppContext";
import { filterLiveStream, latestEntry } from "../../utils/logStreams";
import { escapeHtml, formatTs } from "../../utils";
import { actionSummaryText } from "../../utils/checkpoint";
import { resolvePendingAction } from "../../utils/pendingAction";
import { stageTitleForId } from "../../utils/checkpoint";

export function ActivityTeaser() {
  const {
    activeTab,
    logEntries,
    run,
    jobRunning,
    apiGrants,
    setActiveTab,
    setActivityLogCollapsed,
    setPipelineSubTab,
    selectStage,
    openActionModal,
  } = useApp();

  if (activeTab === "pipeline") return null;

  const live = filterLiveStream(logEntries, run, jobRunning);
  const last = latestEntry(live) || latestEntry(logEntries);
  const summary = actionSummaryText(run, apiGrants);
  const pending = resolvePendingAction(run, apiGrants);
  const runningTitle =
    jobRunning && run?.job
      ? stageTitleForId(run.stages, run.job.current_stage || run.job.stage)
      : null;

  const goAttention = () => {
    if (!pending) return;
    setActiveTab("pipeline");
    setPipelineSubTab("stage");
    if (pending.stageId) void selectStage(pending.stageId);
    if (pending.kind !== "handoff") openActionModal();
  };

  return (
    <footer
      className={`activity-teaser log-strip${summary ? " has-attention" : ""}`}
      data-testid="activity-teaser"
      role="log"
      aria-live="polite"
      tabIndex={0}
      onClick={() => {
        if (pending) {
          goAttention();
          return;
        }
        setActiveTab("pipeline");
        setActivityLogCollapsed(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          if (pending) goAttention();
          else {
            setActiveTab("pipeline");
            setActivityLogCollapsed(false);
          }
        }
      }}
    >
      <div className="log-strip-head">
        <span className="log-strip-title">Latest activity</span>
        <span className="log-strip-hint muted">
          {pending ? "Go →" : "Open Pipeline activity →"}
        </span>
      </div>
      <div className="log-strip-body">
        {summary ? (
          <p className="activity-teaser-attention">{summary}</p>
        ) : runningTitle ? (
          <p className="muted">Running — {runningTitle}</p>
        ) : !last ? (
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
